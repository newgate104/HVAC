# data/weather_generator.py
import numpy as np

class SeoulWeatherGenerator:
    """
    Sinh dữ liệu thời tiết Seoul tháng 5–10 (Section 3.3.5)
    Dựa trên TMY data Seoul — phân phối nhiệt độ theo Fig.11(a)
    """
    # Nhiệt độ trung bình tháng Seoul (°C)
    T_MEAN = {5: 18.5, 6: 23.2, 7: 27.0, 8: 27.8, 9: 22.5, 10: 15.8}
    T_STD  = 3.0

    def __init__(self, seed: int = None):
        if seed is not None:
            np.random.seed(seed)

    def generate_day(self, month: int):
        """
        Trả về arrays (96,) cho 1 ngày chia 15min:
        T_oa [°C], omega_oa [kg/kg], q_sol [W/m²], C_PM_oa [μg/m³]
        """
        T_base = self.T_MEAN[month] + self.T_STD * np.random.randn()
        hours  = np.linspace(0, 24, 96, endpoint=False)

        # Nhiệt độ: biên độ ngày ±5°C, đỉnh 14h
        T_oa = T_base - 5.0 * np.cos(2 * np.pi * (hours - 14) / 24)
        T_oa += np.random.normal(0, 0.5, 96)

        # Humidity ratio [kg/kg] — tương quan với nhiệt độ Seoul hè
        omega_oa = 0.012 + 0.001 * (T_oa - 25) / 5
        omega_oa += np.random.normal(0, 0.001, 96)
        omega_oa = np.clip(omega_oa, 0.004, 0.022)

        # Bức xạ mặt trời [W/m²] — sin curve 6h–18h
        q_sol = np.maximum(0.0,
                    600.0 * np.sin(np.pi * (hours - 6) / 12)
                    * ((hours >= 6) & (hours <= 18)).astype(float))
        q_sol += np.random.normal(0, 25, 96)
        q_sol = np.clip(q_sol, 0, 900)

        # PM2.5 ngoài trời — Fig.11(b): mean≈18, std≈12 μg/m³
        pm25_base = np.clip(np.random.lognormal(2.7, 0.65), 1, 80)
        C_PM_oa   = np.ones(96) * pm25_base
        C_PM_oa  += np.random.normal(0, 1.5, 96)
        C_PM_oa   = np.clip(C_PM_oa, 0, 80)

        return T_oa, omega_oa, q_sol, C_PM_oa
