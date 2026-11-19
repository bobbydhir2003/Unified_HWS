import { useQuery } from "@tanstack/react-query";
import { get } from "./api";

export type ClinicFull = {
  id: string; name: string; code: string; timezone: string; phone: string | null; address_line1: string | null;
  city: string | null; state: string | null; postal_code: string | null; rooms: string[]; is_active: boolean;
};

export function useClinics(includeInactive = false) {
  return useQuery({ queryKey: ["clinics", includeInactive], queryFn: () => get<ClinicFull[]>("/clinics", { include_inactive: includeInactive }), staleTime: 60_000 });
}

export function useRooms(clinicId?: string | null) {
  const { data } = useClinics();
  return data?.find((c) => c.id === clinicId)?.rooms ?? [];
}
