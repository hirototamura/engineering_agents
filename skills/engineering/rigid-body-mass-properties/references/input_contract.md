# Input contract

parts: unique id, mass_kg (null if unknown), center_m, shape (box with size_m; annular_cylinder with radii/height; or cad_tensor with reference_mass_kg and inertia_at_com_kg_m2), optional rotation_local_to_body. SI units and data_basis are required.

Keep measured, assumed, derived and synthetic inputs distinct. Supply source references and the operating point/model scope when available. An output inherits the input model limitations; missing data are not inferred as measured values.
