import os
import re
import json
import importlib
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from core.state import AgentState, TravelSlots, Slot, SlotStatus
from core.tools_interface import BundleExplanation

# Динамический импорт клиента промпт-инженера (чтобы Pylance/VS Code не выдавал 2 ошибки импорта)
pe_extract_slots = None
pe_generate_question = None
pe_explain_candidates = None
HAS_PE_MODULE = False

for mod_name in ("src.qwen_client", "qwen_prompt_only.src.qwen_client"):
    try:
        _mod = importlib.import_module(mod_name)
        pe_extract_slots = getattr(_mod, "extract_slots", None)
        pe_generate_question = getattr(_mod, "generate_question", None)
        pe_explain_candidates = getattr(_mod, "explain_candidates", None)
        if pe_extract_slots and pe_generate_question and pe_explain_candidates:
            HAS_PE_MODULE = True
            break
    except ImportError:
        continue


# Настройки подключения к Ollama / Qwen
OLLAMA_HOST = os.getenv("OLLAMA_HOST", os.getenv("LLM_BASE_URL", "http://localhost:11434")).rstrip("/")
if OLLAMA_HOST.endswith("/v1"):
    OLLAMA_HOST = OLLAMA_HOST[:-3]
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "qwen2.5:7b-instruct"))

BASE_DIR = Path(__file__).resolve().parent.parent

# Словарь перевода английских категорий activity из промпта в русские маркеры для эвристик ядра
ACTIVITY_TRANSLATION_MAP: Dict[str, str] = {
    "beach": "beach (тёплое море, пляж, покупаться)",
    "ski": "ski (горы, горные лыжи, сноуборд)",
    "culture": "culture (экскурсии, музеи, архитектура)",
    "nature": "nature (горы, природа, походы)",
    "spa": "spa (термы, спа, релакс)",
    "quiet": "quiet (тишина, спокойный отдых, релакс)",
    "romance": "romance (романтическая поездка, море)",
    "food": "food (гастротур, экскурсии)",
    "nightlife": "nightlife (клубы, вечеринки, пляж)",
    "family": "family (семейный отдых с детьми, море)",
    "wellness": "wellness (спа, термы, горы)",
    "adventure": "adventure (активный отдых, горы)",
}

VISA_TRANSLATION_MAP: Dict[str, str] = {
    "visa_free_only": "без визы",
    "has_schengen": "виза есть (шенген)",
    "visa_not_important": "любая виза",
    "needs_visa_help": "нужна помощь с визой",
}

TRANSPORT_TRANSLATION_MAP: Dict[str, str] = {
    "plane": "flight",
    "flight": "flight",
    "train": "train",
    "car": "car",
    "bus": "bus",
    "any": "any",
}

# Встроенный системный промпт на случай, если папка prompts/ с .txt файлами ещё не скопирована
DEFAULT_SLOT_SYSTEM_PROMPT = """Ты — NLU-модуль туристического AI-агента.
Извлеки параметры поездки из сообщения пользователя и верни СТРОГИЙ JSON формата:
{
  "message_intent": "TRAVEL_REQUEST",
  "slots": {
    "origin": {"value": "Москва", "status": "YES", "change": "SET"},
    "destination": {"value": null, "status": "NO", "change": "KEEP"},
    "date": {"value": null, "status": "NO", "change": "KEEP"},
    "month": {"value": "ноябрь", "status": "YES", "change": "SET"},
    "season": {"value": null, "status": "NO", "change": "KEEP"},
    "nights": {"value": 7, "status": "VAGUE", "change": "SET"},
    "activity": {"value": "beach", "status": "VAGUE", "change": "SET"},
    "budget_max": {"value": 100000, "status": "YES", "change": "SET"},
    "guest_adults": {"value": 2, "status": "VAGUE", "change": "KEEP"},
    "guest_children": {"value": 0, "status": "NO", "change": "KEEP"},
    "total_guests": {"value": 2, "status": "VAGUE", "change": "KEEP"},
    "pets": {"value": "with_pet", "status": "YES", "change": "SET"},
    "hotel_stars": {"value": 4, "status": "YES", "change": "SET"},
    "visa_preference": {"value": null, "status": "NO", "change": "KEEP"},
    "transport_type": {"value": "plane", "status": "VAGUE", "change": "KEEP"}
  }
}
Допустимые status: "YES", "VAGUE", "NO".
Допустимые activity: "beach", "ski", "culture", "nature", "spa".
Если параметр не упомянут и не был в current_slots — ставь status="NO", value=null.
"""


class LLMClient:
    """
    Связующий клиент между Qwen NLU (работой промпт-инженера / Ollama)
    и детерминированным ядром Agent Core (State Machine).
    """

    def __init__(self, host: str = OLLAMA_HOST, model: str = OLLAMA_MODEL, strict: bool = False, fast: bool = False):
        self.strict = strict
        self.fast = fast
        self.host = host
        self.model = model

        # Загружаем все 3 промпта коллеги (проверяем оба варианта имен файлов)
        self.slot_prompt = self._load_prompt(["qwen_slot_extraction.txt", "slot_extraction.txt"]) or DEFAULT_SLOT_SYSTEM_PROMPT
        if self.fast:
            self.slot_prompt = self._load_prompt(["fast_slot_extraction.txt"]) or self.slot_prompt
        self.question_prompt = self._load_prompt(["qwen_question_generation.txt", "question_generation.txt"])
        self.explanation_prompt = self._load_prompt(["qwen_explanation.txt", "explanation.txt"])

        # Хранилище полных данных последнего ответа модели (28 слотов для БД бэкендера)
        self.last_message_intent: str = "TRAVEL_REQUEST"
        self.last_raw_qwen_slots: Dict[str, Any] = {}
        self.last_cleared_slots: List[str] = []

    def _load_prompt(self, filenames: List[str]) -> str:
        """Ищет файл промпта в папках prompts/, qwen_prompt_only/prompts/ и корне проекта."""
        search_dirs = [
            BASE_DIR / "prompts",
            BASE_DIR / "qwen_prompt_only" / "prompts",
            BASE_DIR,
        ]
        for directory in search_dirs:
            for fname in filenames:
                candidate = directory / fname
                if candidate.exists():
                    return candidate.read_text(encoding="utf-8")
        return ""

    def _clean_json_text(self, text: str) -> str:
        """Удаляет возможные обёртки ```json ... ``` из ответа модели."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
        return cleaned.strip()

    def _call_ollama_json(self, system_prompt: str, user_payload: Dict[str, Any], timeout: float = 120.0, max_tokens: int | None = None) -> Dict[str, Any]:
        """Calls the OpenAI-compatible Ollama /v1/chat/completions endpoint."""
        url = f"{self.host}/v1/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            "response_format": {"type": "json_object"},
            "stream": False,
            "temperature": 0.1,
        }
        if max_tokens is not None or self.fast:
            body["max_tokens"] = max_tokens if max_tokens is not None else 768
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            resp_data = json.loads(response.read().decode("utf-8"))
            if resp_data["choices"][0].get("finish_reason") == "length":
                raise ValueError("Model output exceeded token budget")
            raw_content = resp_data["choices"][0]["message"]["content"]
            return json.loads(self._clean_json_text(raw_content))

    # =========================================================================
    # 1. ИЗВЛЕЧЕНИЕ СЛОТОВ (qwen_slot_extraction.txt -> TravelSlots)
    # =========================================================================
    def extract_slots(
        self,
        user_message: str,
        state: Optional[AgentState] = None,
        pending_slot: Optional[str] = None,
    ) -> TravelSlots:
        """
        Принимает сообщение пользователя и текущий AgentState.
        Вызывает Qwen и возвращает TravelSlots для ядра.
        """
        current_slots_context = self._build_current_slots_context(state) if state else {}
        last_question = state.clarification_question if state else None

        # Автоопределение pending_slot по последнему вопросу блокера
        if pending_slot is None and last_question:
            q_low = last_question.lower()
            if "откуда" in q_low or "из какого города" in q_low:
                pending_slot = "origin"
            elif "дат" in q_low or "месяц" in q_low:
                pending_slot = "month"
            elif "куда" in q_low or "формат отдыха" in q_low:
                pending_slot = "activity"

        try:
            # Вариант А: вызов через модуль промпт-инженера src.qwen_client (если подключен)
            if not self.strict and HAS_PE_MODULE and pe_extract_slots is not None:
                pe_result = pe_extract_slots(
                    user_message,
                    current_date=str(date.today()),
                    current_slots=current_slots_context,
                    pending_slot=pending_slot,
                    last_assistant_question=last_question,
                )
                raw_dict = pe_result.model_dump(mode="json")
            # Вариант Б: прямой вызов Ollama
            else:
                payload = {
                    "current_date": str(date.today()),
                    "user_message": user_message,
                    "current_slots": current_slots_context,
                    "pending_slot": pending_slot,
                    "last_assistant_question": last_question,
                }
                raw_dict = self._call_ollama_json(self.slot_prompt, payload)

            self.last_message_intent = raw_dict.get("message_intent", "TRAVEL_REQUEST")
            self.last_raw_qwen_slots = raw_dict.get("slots", {})

            # Если пользователь попросил начать заново (RESET) — очищаем состояние
            if self.last_message_intent == "RESET" and state is not None:
                state.slots = TravelSlots()
                state.recommendations = []
                state.clarification_count = 0

            extracted = self._map_28_slots_to_core(self.last_raw_qwen_slots, user_message, state)

            # Если модель вернула совсем пустой ответ, подстраховываем регулярками
            if not self.strict and all(getattr(extracted, f).status == SlotStatus.NO for f in TravelSlots.model_fields.keys()):
                return self._fallback_regex_extract(user_message, pending_slot=pending_slot)
            return extracted

        except Exception:
            if self.strict:
                raise
            # Безотказный эвристический парсер (если Ollama выключена или таймаут)
            return self._fallback_regex_extract(user_message, pending_slot=pending_slot)

    def _build_current_slots_context(self, state: AgentState) -> Dict[str, Any]:
        """Формирует компактный словарь уже известных слотов для подачи на вход Qwen."""
        ctx: Dict[str, Any] = {}
        s = state.slots
        if s.origin.value:
            ctx["origin"] = s.origin.value
        if s.destination.value:
            ctx["destination"] = s.destination.value
        if s.dates.value:
            ctx["month"] = s.dates.value
        if s.vibe.value:
            ctx["activity"] = s.vibe.value
        if s.budget.value:
            ctx["budget_max"] = s.budget.value
        if s.pet_friendly.value is True:
            ctx["pets"] = "with_pet"
        if s.stars.value:
            ctx["hotel_stars"] = s.stars.value
        return ctx

    def _map_28_slots_to_core(
        self,
        qwen_slots: Dict[str, Dict[str, Any]],
        raw_text: str,
        state: Optional[AgentState] = None,
    ) -> TravelSlots:
        """
        Конвертирует 28 детальных слотов промпт-инженера (с полями value, status, change)
        в 10 слотов модели TravelSlots вашего ядра.
        """
        core = TravelSlots()
        self.last_cleared_slots = []

        def is_active(slot_name: str) -> Tuple[bool, Any, SlotStatus]:
            item = qwen_slots.get(slot_name) or {}
            if not isinstance(item, dict):
                return False, None, SlotStatus.NO
            status_str = item.get("status", "NO")
            change_str = item.get("change", "KEEP")
            val = item.get("value")

            if change_str == "CLEAR":
                self.last_cleared_slots.append(slot_name)
                return False, None, SlotStatus.NO

            if status_str in ("YES", "VAGUE") and val is not None:
                st = SlotStatus.YES if status_str == "YES" else SlotStatus.VAGUE
                return True, val, st
            return False, None, SlotStatus.NO

        # 1. Origin (город отправления)
        ok, val, st = is_active("origin")
        if ok:
            core.origin = Slot(value=str(val), status=st, raw_text=raw_text)

        # 2. Destination (destination -> city -> destination_country)
        for dest_key in ("destination", "city", "destination_country"):
            ok, val, st = is_active(dest_key)
            if ok:
                core.destination = Slot(value=str(val), status=st, raw_text=raw_text)
                break

        # 3. Dates (date -> month -> season + nights)
        for date_key in ("date", "month", "season"):
            ok, val, st = is_active(date_key)
            if ok:
                date_str = str(val)
                ok_n, nights_val, _ = is_active("nights")
                if ok_n:
                    date_str = f"{date_str} ({nights_val} ночей)"
                core.dates = Slot(value=date_str, status=st, raw_text=raw_text)
                break

        # 4. Vibe / Activity
        ok, val, st = is_active("activity")
        if ok:
            act_raw = str(val).strip()
            enriched_parts = [
                ACTIVITY_TRANSLATION_MAP.get(part.strip(), part.strip())
                for part in act_raw.split("+")
            ]
            vibe_status = SlotStatus.VAGUE if core.destination.status == SlotStatus.NO else st
            core.vibe = Slot(value=", ".join(enriched_parts), status=vibe_status, raw_text=raw_text)

        # 5. Budget (budget_max)
        ok, val, st = is_active("budget_max")
        if ok:
            if val == "CHEAPER_THAN_PREVIOUS" and state and isinstance(state.slots.budget.value, int):
                new_b = max(40000, int(state.slots.budget.value * 0.75))
                core.budget = Slot(value=new_b, status=SlotStatus.YES, raw_text=raw_text)
            else:
                core.budget = Slot(value=val, status=st, raw_text=raw_text)

        # 6. Guests (guest_adults, guest_children, total_guests)
        ok_a, adults, st_a = is_active("guest_adults")
        ok_c, children, st_c = is_active("guest_children")
        ok_t, total_g, st_t = is_active("total_guests")
        if ok_a or ok_c:
            parts = []
            if ok_a:
                parts.append(f"взрослых: {adults}")
            if ok_c:
                parts.append(f"детей: {children}")
            core.guests = Slot(value=", ".join(parts), status=st_a if ok_a else st_c, raw_text=raw_text)
        elif ok_t:
            core.guests = Slot(value=f"гостей: {total_g}", status=st_t, raw_text=raw_text)

        # 7. Pet-friendly (pets: "with_pet" / "no_pet" / CLEAR)
        ok_p, pet_val, _ = is_active("pets")
        if ok_p:
            has_pet = str(pet_val).lower() not in ("no_pet", "false", "0", "нет")
            core.pet_friendly = Slot(value=has_pet, status=SlotStatus.YES, raw_text=raw_text)
        elif "pets" in self.last_cleared_slots and state is not None:
            state.slots.pet_friendly = Slot(value=False, status=SlotStatus.NO)
            state.cart.is_hotel_valid = False

        # 8. Hotel Stars (hotel_stars)
        ok_s, stars_val, st_s = is_active("hotel_stars")
        if ok_s:
            core.stars = Slot(value=stars_val, status=st_s, raw_text=raw_text)
        elif "hotel_stars" in self.last_cleared_slots and state is not None:
            state.slots.stars = Slot(value=None, status=SlotStatus.NO)
            state.cart.is_hotel_valid = False

        # 9. Visa (visa_preference)
        ok_v, visa_val, st_v = is_active("visa_preference")
        if ok_v:
            mapped_visa = VISA_TRANSLATION_MAP.get(str(visa_val), str(visa_val))
            core.visa = Slot(value=mapped_visa, status=st_v, raw_text=raw_text)

        # 10. Transport (transport_type)
        ok_tr, tr_val, st_tr = is_active("transport_type")
        if ok_tr:
            mapped_tr = TRANSPORT_TRANSLATION_MAP.get(str(tr_val), str(tr_val))
            core.transport = Slot(value=mapped_tr, status=st_tr, raw_text=raw_text)

        return core

    # =========================================================================
    # 2. ГЕНЕРАЦИЯ УТОЧНЯЮЩЕГО ВОПРОСА (qwen_question_generation.txt)
    # =========================================================================
    def generate_clarification_question(
        self,
        blocking_fields: List[str],
        state: AgentState,
    ) -> str:
        """
        Принимает список недостающих блокеров от Python State Machine (например, ['origin'])
        и генерирует ровно 1 живой уточняющий вопрос.
        """
        if not blocking_fields:
            return ""

        slots_payload = {
            "origin": {"value": state.slots.origin.value, "status": state.slots.origin.status.value},
            "month": {"value": state.slots.dates.value, "status": state.slots.dates.status.value},
            "destination": {"value": state.slots.destination.value, "status": state.slots.destination.status.value},
            "activity": {"value": state.slots.vibe.value, "status": state.slots.vibe.status.value},
        }

        try:
            if not self.strict and HAS_PE_MODULE and pe_generate_question is not None:
                res = pe_generate_question(blocking_fields=blocking_fields, slots=slots_payload)
                q_text = getattr(res, "question", "")
            elif self.question_prompt:
                payload = {"blocking_fields": blocking_fields, "slots": slots_payload}
                data = self._call_ollama_json(self.question_prompt, payload, timeout=120.0)
                q_text = data.get("question", "")
            else:
                q_text = ""

            if q_text and len(q_text.strip()) > 3:
                return q_text.strip()
        except Exception:
            if self.strict:
                raise
            pass

        # Надёжный детерминированный fallback, если модель недоступна
        first_blocker = blocking_fields[0]
        if first_blocker == "origin":
            return "Подскажите, из какого города вы планируете вылет или выезд?"
        if first_blocker in ("dates", "month", "date"):
            return "На какие даты или в каком месяце планируется поездка?"
        return (
            "Куда бы вы хотели отправиться или какой формат отдыха вам ближе "
            "(например, тёплое море, горы, экскурсии)?"
        )

    # =========================================================================
    # 3. ОБЪЯСНЕНИЕ РЕКОМЕНДАЦИЙ (qwen_explanation.txt -> BundleExplanation)
    # =========================================================================
    def enrich_bundles_with_explanations(self, state: AgentState) -> None:
        """
        Прогоняет найденные в state.recommendations бандлы через промпт qwen_explanation.txt
        и обновляет блоки Why / Trade-offs / Risks.
        """
        if not state.recommendations:
            return

        user_prefs = self._build_current_slots_context(state)
        candidates = []
        for b in state.recommendations:
            candidates.append({
                "candidate_id": b.get("bundle_id"),
                "destination": b.get("destination"),
                "price_total": b.get("price_total"),
                "hotel": b.get("hotel"),
                "transport": b.get("transport"),
                "transfer": b.get("transfer"),
                "data_source": "synthetic",
            })

        try:
            if not self.strict and HAS_PE_MODULE and pe_explain_candidates is not None:
                res = pe_explain_candidates(
                    user_preferences=user_prefs,
                    assumptions=state.applied_heuristics,
                    candidates=candidates,
                )
                raw_recs = res.model_dump(mode="json").get("recommendations", [])
            elif self.explanation_prompt:
                payload = {
                    "user_preferences": user_prefs,
                    "assumptions": state.applied_heuristics,
                    "candidates": candidates,
                }
                data = self._call_ollama_json(self.explanation_prompt, payload, timeout=120.0)
                raw_recs = data.get("recommendations", [])
            else:
                return

            expl_by_id = {item.get("candidate_id"): item for item in raw_recs if item.get("candidate_id")}

            for b in state.recommendations:
                cid = b.get("bundle_id")
                if cid in expl_by_id:
                    item = expl_by_id[cid]
                    why_str = item.get("why_it_fits") or b["explanation"]["why"]
                    tradeoffs_list = item.get("tradeoffs") or []
                    warnings_list = (item.get("data_warnings") or []) + (item.get("assumptions") or [])

                    tradeoffs_str = "; ".join(tradeoffs_list) if tradeoffs_list else b["explanation"]["tradeoffs"]
                    risks_str = "; ".join(warnings_list) if warnings_list else b["explanation"]["risks"]

                    b["explanation"] = BundleExplanation(
                        why=why_str,
                        tradeoffs=tradeoffs_str,
                        risks=risks_str,
                    ).model_dump()
        except Exception:
            if self.strict:
                raise
            return

    # =========================================================================
    # 4. АВТОНОМНЫЙ REGEX-FALLBACK (ПОЛНЫЙ СПИСОК 46 ГОРОДОВ ЕВРОПЫ И РФ)
    # =========================================================================
    def _fallback_regex_extract(self, text: str, pending_slot: Optional[str] = None) -> TravelSlots:
        """Резервный парсер русских фраз на случай отсутствия запущенной Ollama."""
        slots = TravelSlots()
        text_l = text.lower().strip()

        city_patterns = {
            "москв": "Москва", "мск": "Москва",
            "питер": "Санкт-Петербург", "спб": "Санкт-Петербург", "петербург": "Санкт-Петербург",
            "казан": "Казань", "екатеринбург": "Екатеринбург", "екб": "Екатеринбург",
            "сочи": "Сочи", "париж": "Париж", "рим": "Рим", "ницц": "Ницца",
            "барселон": "Барселона", "инсбрук": "Инсбрук", "церматт": "Церматт",
            "вен": "Вена", "праг": "Прага", "мюнхен": "Мюнхен", "милан": "Милан",
            "осло": "Осло", "флоренц": "Флоренция", "мадрид": "Мадрид", "берлин": "Берлин",
            "лондон": "Лондон", "анси": "Анси", "больцано": "Больцано", "интерлакен": "Интерлакен",
            "уиндермир": "Уиндермир", "сан-марино": "Сан-Марино", "виши": "Виши",
            "монтекатини": "Монтекатини-Терме", "баден": "Баден-Баден", "гастайн": "Бад-Гастайн",
            "рагац": "Бад-Рагац", "карлов": "Карловы Вары", "будапешт": "Будапешт",
            "сьерра": "Сьерра-Невада", "шамони": "Шамони-Монблан", "кортин": "Кортина-д’Ампеццо",
            "гармиш": "Гармиш-Партенкирхен", "андорр": "Андорра-ла-Велья", "палерм": "Палермо",
            "малаг": "Малага", "хань": "Ханья", "крит": "Ханья", "фару": "Фару",
            "монте-карло": "Монте-Карло", "монако": "Монте-Карло", "белград": "Белград",
            "копаоник": "Копаоник", "врнячк": "Врнячка-Баня", "будв": "Будва",
            "жабляк": "Жабляк", "сараев": "Сараево", "яхорин": "Яхорина",
            "дубай": "ОАЭ (Дубай)", "египет": "Египет (Шарм-эш-Шейх)", "шарм": "Египет (Шарм-эш-Шейх)",
        }

        for token, canonical in city_patterns.items():
            if f"из {token}" in text_l or f"с {token}" in text_l or (pending_slot == "origin" and token in text_l):
                slots.origin = Slot(value=canonical, status=SlotStatus.YES, raw_text=text)
            elif f"в {token}" in text_l or f"на {token}" in text_l or (pending_slot in ("destination", "activity") and token in text_l):
                slots.destination = Slot(value=canonical, status=SlotStatus.YES, raw_text=text)
            elif text_l == token:
                if pending_slot == "origin":
                    slots.origin = Slot(value=canonical, status=SlotStatus.YES, raw_text=text)
                else:
                    slots.destination = Slot(value=canonical, status=SlotStatus.YES, raw_text=text)

        # Месяцы и даты
        months = ["январ", "феврал", "март", "апрел", "мае", "мая", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"]
        for m in months:
            if m in text_l:
                slots.dates = Slot(value=m, status=SlotStatus.YES, raw_text=text)
                break
        if slots.dates.status == SlotStatus.NO and "выходн" in text_l:
            slots.dates = Slot(value="выходные", status=SlotStatus.YES, raw_text=text)

        # Вайб / Активности
        if any(w in text_l for w in ["мор", "морэ", "пляж", "купат", "тепл"]):
            slots.vibe = Slot(value=ACTIVITY_TRANSLATION_MAP["beach"], status=SlotStatus.VAGUE, raw_text=text)
        elif any(w in text_l for w in ["гор", "лыж", "сноуборд"]):
            slots.vibe = Slot(value=ACTIVITY_TRANSLATION_MAP["ski"], status=SlotStatus.VAGUE, raw_text=text)
        elif any(w in text_l for w in ["спа", "терм", "источник", "релакс"]):
            slots.vibe = Slot(value=ACTIVITY_TRANSLATION_MAP["spa"], status=SlotStatus.VAGUE, raw_text=text)
        elif any(w in text_l for w in ["экскурс", "музе", "архитектур", "гулят"]):
            slots.vibe = Slot(value=ACTIVITY_TRANSLATION_MAP["culture"], status=SlotStatus.VAGUE, raw_text=text)

        # Бюджет
        digits = re.findall(r"\d+", text_l)
        if any(w in text_l for w in ["недорог", "недораг", "дешев", "бюджетн", "эконом"]):
            slots.budget = Slot(value="недорого", status=SlotStatus.VAGUE, raw_text=text)
        elif "полтинник" in text_l:
            slots.budget = Slot(value=50000, status=SlotStatus.YES, raw_text=text)
        elif digits and any(w in text_l for w in ["тыс", "к", "рубл", "бюджет", "за ", "000"]):
            val = int(digits[-1])
            if val < 1000:
                val *= 1000
            slots.budget = Slot(value=val, status=SlotStatus.YES, raw_text=text)

        # Питомцы
        if any(w in text_l for w in ["собак", "пёс", "пес", "шпиц", "корги", "кот", "питомц", "животн"]):
            slots.pet_friendly = Slot(value=True, status=SlotStatus.YES, raw_text=text)

        # Звёзды
        star_match = re.search(r"([345])\s*(?:звезд|\*)", text_l)
        if star_match:
            slots.stars = Slot(value=int(star_match.group(1)), status=SlotStatus.YES, raw_text=text)

        # Виза
        if "без виз" in text_l or "безвиз" in text_l:
            slots.visa = Slot(value="без визы", status=SlotStatus.YES, raw_text=text)

        return slots