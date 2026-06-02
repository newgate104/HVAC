# simulator/building_envelope.py
import numpy as np

class BuildingEnvelopeModel:
    """
    2R2C model theo Eq.(7)–(9) của bài báo
    dTza/dt = (Tw-Tza)/Rzw + (Toa-Tza)/Rzo + q_sol*beta*Awin + Q_hvac + Q_gain
    dTw/dt  = (Tza-Tw)/Rzw + q_sol*(1-beta)*Awin
    """
    def __init__(self):
        # Thông số calibrate từ FLEXLAB test cell
        self.Cza  = 3.8e6   # J/K  — nhiệt dung vùng không khí
        self.Cw   = 8.5e6   # J/K  — nhiệt dung tường
        self.Rzw  = 0.012   # K/W  — nhiệt trở tường-phòng
        self.Rzo  = 0.008   # K/W  — nhiệt trở ngoài-phòng
        self.beta = 0.3     # [-]  — phần bức xạ mặt trời phòng hấp thụ
        self.Awin = 5.5     # m²   — diện tích cửa sổ hiệu dụng
        self.cp_a = 1006.0  # J/(kg·K)
        self.rho_a = 1.2    # kg/m³

    def step(self, Tza, Tw, Toa, q_sol, Q_hvac, Q_gain, dt=900):
        """
        dt: bước thời gian 900s = 15 phút (Section 3.3.1)
        Returns: Tza_new, Tw_new
        """
        dTza_dt = ((Tw - Tza) / self.Rzw
                   + (Toa - Tza) / self.Rzo
                   + q_sol * self.beta * self.Awin
                   + Q_hvac + Q_gain) / self.Cza

        dTw_dt  = ((Tza - Tw) / self.Rzw
                   + q_sol * (1 - self.beta) * self.Awin) / self.Cw

        Tza_new = Tza + dTza_dt * dt
        Tw_new  = Tw  + dTw_dt  * dt
        return Tza_new, Tw_new

    def calc_Q_hvac(self, V_sa, T_sa, Tza):
        """Eq.(9): nhiệt lạnh từ HVAC vào phòng"""
        return self.cp_a * self.rho_a * V_sa * (T_sa - Tza)
