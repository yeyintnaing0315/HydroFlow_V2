import type { BagoAreasResponse } from "../types";

export function preferredTownshipId(districts: BagoAreasResponse["districts"]): string {
  const bagoDistrict = districts.find((district) => district.name_en === "Bago");
  const bagoTownship = bagoDistrict?.townships.find((township) => township.name_en === "Bago");
  return bagoTownship?.id ?? districts[0]?.townships[0]?.id ?? "";
}
