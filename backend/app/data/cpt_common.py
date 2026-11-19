"""Common outpatient CPT/HCPCS codes with default fees (cents). CPT is AMA-licensed: production needs a license and
the full code set; these descriptions are abbreviated for development."""

CPT_DEFAULTS = [
    ("99202", "Office visit, new patient, straightforward", 11000), ("99203", "Office visit, new patient, low complexity", 16500),
    ("99204", "Office visit, new patient, moderate complexity", 24500), ("99205", "Office visit, new patient, high complexity", 32000),
    ("99212", "Office visit, established, straightforward", 7500), ("99213", "Office visit, established, low complexity", 12000),
    ("99214", "Office visit, established, moderate complexity", 17500), ("99215", "Office visit, established, high complexity", 24000),
    ("99395", "Preventive visit, established, 18-39", 21000), ("99396", "Preventive visit, established, 40-64", 23000),
    ("99397", "Preventive visit, established, 65+", 24500), ("99441", "Telephone E/M, 5-10 min", 5500),
    ("36415", "Venipuncture", 1500), ("81002", "Urinalysis, non-automated", 1200), ("87880", "Rapid strep test", 2500),
    ("93000", "Electrocardiogram, complete", 5500), ("90471", "Immunization administration", 3000), ("96127", "Brief behavioral assessment (e.g. PHQ)", 1500),
]
EM_ESTABLISHED = ["99212", "99213", "99214", "99215"]
EM_NEW = ["99202", "99203", "99204", "99205"]
