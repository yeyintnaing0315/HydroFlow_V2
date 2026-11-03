from app.services.allocation_rules import FUND_MMK_PER_PERSON, line_items_per_served_person


def test_per_person_items_and_gender_clothes() -> None:
    scored = {"expected_affected_people": 100, "expected_households": 20}
    items = line_items_per_served_person(scored, "Bago")
    by_code = {(item.category_code, item.item_code): item for item in items}
    assert by_code[("foods", "rice")].requested == 100
    assert by_code[("fund", None)].requested == 100 * FUND_MMK_PER_PERSON
    assert (
        by_code[("clothing", "m_longyi")].requested
        + by_code[("clothing", "f_longyi")].requested
        == 100
    )
    assert len(items) == 19
    assert by_code[("kitchenware", "bowl")].requested == 100
    assert by_code[("utilities", "bednet")].requested == 100
