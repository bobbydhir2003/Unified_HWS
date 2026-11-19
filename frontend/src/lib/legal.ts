/**
 * Central copyright / legal constants — the single source for the footer, About & legal page, build banner and HTML
 * metadata. Do not hardcode these strings elsewhere.
 * © 2026 Sidra Riaz Awan. All rights reserved.
 */
export const COPYRIGHT_HOLDER = "Sidra Riaz Awan";
export const COPYRIGHT_YEAR = 2026;
export const COPYRIGHT_NOTICE = `© ${COPYRIGHT_YEAR} ${COPYRIGHT_HOLDER}. All rights reserved.`;
export const PRODUCT_NAME = "Undeclared";
export const PRODUCT_DESCRIPTION = "Unified hospital management system";

/** Open-source components keep their own licenses; this list is informational (see each package for full terms). */
export const THIRD_PARTY = [
  { name: "React", license: "MIT" }, { name: "React Router", license: "MIT" }, { name: "TanStack Query", license: "MIT" },
  { name: "Radix UI", license: "MIT" }, { name: "Tailwind CSS", license: "MIT" }, { name: "Lucide icons", license: "ISC" },
  { name: "Inter typeface", license: "SIL Open Font License 1.1" }, { name: "Recharts", license: "MIT" }, { name: "date-fns", license: "MIT" },
  { name: "Zod", license: "MIT" }, { name: "FastAPI", license: "MIT" }, { name: "SQLAlchemy", license: "MIT" }, { name: "Pydantic", license: "MIT" },
  { name: "Celery", license: "BSD-3-Clause" }, { name: "PostgreSQL", license: "PostgreSQL License" },
];

/** Clinical code sets are owned by their publishers and are not covered by the notice above. */
export const CODE_SET_NOTICES = [
  "CPT® is a registered trademark of the American Medical Association; CPT codes and descriptions are © AMA. This development build uses an abbreviated list; production use requires an AMA license.",
  "LOINC® is a registered trademark of Regenstrief Institute, Inc.; LOINC codes are © Regenstrief Institute.",
  "ICD-10-CM is published by the U.S. National Center for Health Statistics (public domain).",
];
