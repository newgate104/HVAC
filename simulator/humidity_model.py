# simulator/humidity_model.py
import numpy as np

class HumidityModel:
    """
    Eq.(11): rho_a * V * d(omega_za)/dt = rho_a*V_sa*(omega_sa - omega_za) + S_omega
    """
    def __init__(self):
        self.rho_a = 1.2    # kg/m³
        self.V     = 56 * 4.88  # m³ — thể tích phòng (56m² × 4.88m cao)

    def step(self, omega_za, omega_sa, V_sa, S_omega, dt=900):
        """
        omega: kg H2O / kg dry air
        S_omega: tốc độ sinh ẩm từ người = 2.43e-5 kg/s/người × số người (Table 3)
        """
        d_omega_dt = (self.rho_a * V_sa * (omega_sa - omega_za) + S_omega) \
                     / (self.rho_a * self.V)
        return omega_za + d_omega_dt * dt
