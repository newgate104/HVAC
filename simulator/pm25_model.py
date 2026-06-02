# simulator/pm25_model.py

class PM25Model:
    """
    Eq.(14): V * dC_PM_za/dt =
        V_oa*(1-eta1)*(1-eta2)*C_PM_oa
        - (V_oa + eta2*V_ra + kd*V + CADR)*C_PM_za
        + S_PM
    """
    def __init__(self):
        self.V    = 56 * 4.88   # m³
        self.eta1 = 0.07        # hiệu suất pre-filter MERV 6 (Table 4)
        self.eta2 = 0.26        # hiệu suất final filter MERV 8 (Table 4)
        self.kd   = 1.94e-4     # 1/s — tốc độ lắng đọng (Table 4)
        self.CADR_on  = 0.181   # m³/s — air purifier ON (Table 4)
        self.CADR_off = 0.0
        self.S_PM = 0.0         # nguồn PM2.5 nội thất ≈ 0 (Table 4)

    def step(self, C_PM_za, C_PM_oa, V_oa, V_ra, P_air, dt=900):
        """
        P_air: 1 = ON, 0 = OFF
        """
        CADR = self.CADR_on if P_air else self.CADR_off

        source = V_oa * (1 - self.eta1) * (1 - self.eta2) * C_PM_oa
        sink   = (V_oa + self.eta2 * V_ra + self.kd * self.V + CADR) * C_PM_za

        dC_dt = (source - sink + self.S_PM) / self.V
        return max(0.0, C_PM_za + dC_dt * dt)
