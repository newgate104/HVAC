# simulator/co2_model.py

class CO2Model:
    """
    Eq.(13): V * dC_CO2_za/dt = V_oa*(C_CO2_oa - C_CO2_za) + 1e6 * S_CO2
    """
    def __init__(self):
        self.V = 56 * 4.88  # m³

    def step(self, C_CO2_za, C_CO2_oa, V_oa, S_CO2, dt=900):
        """
        C_CO2: ppm
        V_oa: m³/s — lưu lượng gió ngoài
        S_CO2: m³/s/người × số người = 5.2e-6 × N_occ (Table 3)
        """
        dC_dt = (V_oa * (C_CO2_oa - C_CO2_za) + 1e6 * S_CO2) / self.V
        return C_CO2_za + dC_dt * dt
