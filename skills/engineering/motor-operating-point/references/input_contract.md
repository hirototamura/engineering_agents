# Input contract

motor_convention=effective_dc; torque_constant_N_m_A, back_emf_V_s_rad, winding_resistance_ohm, bus_voltage_V, driver_efficiency, current_limit_A, torque_N_m and speed_rad_s. Optional maximum duty, idle power and regeneration capability. SI units and data_basis are required.

Keep measured, assumed, derived and synthetic inputs distinct. Supply source references and the operating point/model scope when available. An output inherits the input model limitations; missing data are not inferred as measured values.
