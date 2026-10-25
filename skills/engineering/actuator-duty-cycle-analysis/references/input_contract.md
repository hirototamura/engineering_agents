# Input contract

Motor operating-point parameters plus motor_count (defaults to one), modes (name, duration_s, torque_N_m, speed_rad_s), ambient_K, thermal_resistance_K_W, thermal_capacity_J_K and maximum_winding_K. Optional initial_winding_K.

Keep measured, assumed, derived and synthetic inputs distinct. Supply source references and the operating point/model scope when available. An output inherits the input model limitations; missing data are not inferred as measured values.
