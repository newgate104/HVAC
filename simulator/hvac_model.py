# simulator/hvac_model.py
import numpy as np

class HVACRegressionModel:
    """
    Steady-state model theo Section 3.4.2 (Eq. 22–24)
    Thay thế FMU Modelica khi không có file .fmu
    Hệ số beta cần calibrate từ dữ liệu thực — dùng giá trị ước tính từ Fig.12
    """
    def __init__(self):
        # Hệ số hồi quy cho V_sa (Eq.22) — calibrate từ Fig.12(a)
        self.b_Vsa = [0.01, 1.15]       # [beta0, beta1]

        # Hệ số cho V_oa fraction (Eq.23) — calibrate từ Fig.12(b)
        self.b_Voa = [-0.05, 1.05]      # [beta0, beta1]

        # Hệ số cho E_fan (Eq.24) — calibrate từ Fig.12(c)
        self.b_Efan = [0.01, -0.02, 0.5, 3.0]  # [b0,b1,b2,b3]

        self.T_sa_sp = 12.5  # °C — setpoint nhiệt độ gió cấp (Section 3.4.2)
        self.phi_sa  = 0.90  # RH gió cấp khi dehumid mode

    def calc_airflow(self, f_sa, D_oa):
        """
        f_sa: fan speed [0–1]
        D_oa: damper opening [0–1]
        Returns: V_sa [m³/s], V_oa [m³/s]
        """
        V_sa = max(0, self.b_Vsa[0] + self.b_Vsa[1] * f_sa)
        frac = max(0, self.b_Voa[0] + self.b_Voa[1] * D_oa)
        V_oa = max(0, frac * V_sa)
        V_ra = V_sa - V_oa
        return V_sa, V_oa, V_ra

    def calc_fan_power(self, f_sa):
        """Eq.(24): E_fan [kW]"""
        b = self.b_Efan
        E = b[0] + b[1]*f_sa + b[2]*f_sa**2 + b[3]*f_sa**3
        return max(0, E)

    def calc_supply_air_state(self, T_mixed, omega_mixed, T_chws):
        """
        Tính trạng thái gió cấp sau coil làm lạnh
        Returns: T_sa [°C], omega_sa [kg/kg]
        """
        # Giả sử điều khiển về setpoint 12.5°C
        T_sa = self.T_sa_sp
        # Nếu cần dehumid: omega_sa tính từ phi_sa=90% tại T_sa
        omega_sa_sat = 0.622 * (0.006112 * np.exp(17.67*T_sa/(T_sa+243.5))) \
                       / (101.325 - 0.006112 * np.exp(17.67*T_sa/(T_sa+243.5)))
        omega_sa = self.phi_sa * omega_sa_sat
        return T_sa, min(omega_sa, omega_mixed)
