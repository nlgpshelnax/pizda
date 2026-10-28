from trip_data.models import Bundle, BundleResult, SearchInput, SearchOutput
from trip_data.providers.catalog import CatalogProvider
from trip_data.validation import total_price, validate_bundle


def search_bundles(payload: SearchInput, catalog: CatalogProvider) -> SearchOutput:
    return build_search_result(payload, catalog.search(payload.request))


def build_search_result(payload: SearchInput, bundles: list[Bundle]) -> SearchOutput:
    options = []
    rejected = {}
    for bundle in bundles:
        issues = validate_bundle(bundle, payload.request)
        if any(issue.severity == "error" for issue in issues):
            rejected[bundle.id] = issues
            continue
        options.append(
            BundleResult(
                bundle=bundle,
                total=total_price(bundle),
                issues=issues,
                reasons=[
                    "Совпадают маршрут, даты и состав гостей",
                    "Включены отель, дорога туда/обратно и два трансфера",
                ],
            )
        )
    options.sort(key=lambda option: option.total.amount)
    return SearchOutput(
        plan_version=payload.plan_version,
        options=options[:5],
        rejected=rejected,
        limitations=[
            "Демо-каталог; нет реального бронирования и подтверждения наличия",
            "Изменение дат/гостей требует отдельной котировки",
            "Сортировка по цене; предпочтения ранжирует модуль AI",
        ],
    )
