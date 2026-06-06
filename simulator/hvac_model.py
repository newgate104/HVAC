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
        Sửa: không luôn dehumid về 12.5°C — chỉ khi thực sự cần.
        """
        # Nhiệt độ gió cấp: bị giới hạn bởi T_chws + deadband (không thể lạnh hơn T_chws)
        T_sa = max(T_chws_sp + 2.0, min(T_mixed, 18.0))  # [T_chws+2, 18]°C

        # omega_sa: chỉ dehumid nếu T_sa đủ thấp để ngưng tụ
        omega_sat_at_Tsa = (0.622 * 0.6112 * np.exp(17.67 * T_sa / (T_sa + 243.5))
                        / (101.325 - 0.6112 * np.exp(17.67 * T_sa / (T_sa + 243.5))))

        if T_sa < 14.0:
            # Dehumidification mode: phi_sa = 90%
            omega_sa = 0.90 * omega_sat_at_Tsa
        else:
            # Sensible cooling only: omega không đổi (không ngưng tụ)
            omega_sa = omega_mixed

        # Không được khô hơn omega_sat
        omega_sa = min(omega_sa, omega_sat_at_Tsa)
        return float(T_sa), float(omega_sa)
