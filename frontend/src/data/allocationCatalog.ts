/** Relief SKUs (matches backend `inventory.DEFAULT_ITEM_TYPES` + fund). */
export const ALLOCATION_CATALOG: {
  category_code: string;
  item_code: string | null;
  name: string;
  unit: string;
}[] = [
  { category_code: "fund", item_code: null, name: "Fund", unit: "mmk" },
  { category_code: "foods", item_code: "rice", name: "Rice", unit: "bag" },
  { category_code: "foods", item_code: "oil", name: "Oil", unit: "bottle" },
  { category_code: "foods", item_code: "canned_fish", name: "Canned fish", unit: "can" },
  { category_code: "clothing", item_code: "tshirt", name: "T-shirt", unit: "piece" },
  { category_code: "clothing", item_code: "m_longyi", name: "Men longyi", unit: "piece" },
  { category_code: "clothing", item_code: "f_longyi", name: "Women longyi", unit: "piece" },
  { category_code: "kitchenware", item_code: "bowl", name: "Bowl", unit: "piece" },
  { category_code: "kitchenware", item_code: "knife", name: "Knife", unit: "piece" },
  { category_code: "kitchenware", item_code: "mug", name: "Mug", unit: "piece" },
  { category_code: "kitchenware", item_code: "spoon", name: "Spoon", unit: "piece" },
  { category_code: "kitchenware", item_code: "soap", name: "Soap", unit: "pack" },
  { category_code: "kitchenware", item_code: "water_dipper", name: "Water dipper", unit: "piece" },
  { category_code: "kitchenware", item_code: "plate", name: "Plate", unit: "piece" },
  { category_code: "kitchenware", item_code: "pot", name: "Pot", unit: "piece" },
  { category_code: "utilities", item_code: "bednet", name: "Bed net", unit: "piece" },
  { category_code: "utilities", item_code: "blanket", name: "Blanket", unit: "piece" },
  { category_code: "utilities", item_code: "towel", name: "Towel", unit: "piece" },
  { category_code: "utilities", item_code: "box", name: "Box", unit: "piece" },
];

export function allocationItemKey(categoryCode: string, itemCode: string | null): string {
  return `${categoryCode}:${itemCode ?? "fund"}`;
}
