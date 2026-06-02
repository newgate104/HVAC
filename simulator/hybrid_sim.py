# simulator/hybrid_simulator.py
import numpy as np
from .building_env import BuildingEnvelopeModel
from .humidity_model import HumidityModel
from .co2_model import CO2Model
from .pm25_model import PM25Model
from .hvac_model import HVACRegressionModel

class HybridSimulator:
    """
    Tích hợp 5 model theo Fig.5 của bài báo
    Input:  state s_t, action a_t
    Output: state s_{t+1}, reward r_t
    """
    # Thông số phòng (Table 3)
    N_OCC_MAX  = 6
    Q_LIG_MAX  = 465.0   # W
    Q_EQP_MAX  = 865.0   # W
    Q_OCC_SEN  = 120.0   # W/person
    S_OCC_MOIS = 2.43e-5 # kg/s/person
    S_OCC_CO2  = 5.2e-6  # m³/s/person
    V_ZONE     = 56 * 4.88

    # Hệ số reward (Section 3.3.2)
    ALPHA = [1.0, 2.5, 5.0, 1.0, 1.0]
    T_U, T_L = 24.5, 22.0   # °C ngưỡng nhiệt độ
    PHI_U    = 0.60          # ngưỡng RH

    def __init__(self):
        self.envelope = BuildingEnvelopeModel()
        self.humidity  = HumidityModel()
        self.co2       = CO2Model()
        self.pm25      = PM25Model()
        self.hvac      = HVACRegressionModel()

        # Trạng thái ẩn
        self.Tw = 24.0  # °C — nhiệt độ khối nhiệt tường

    def _occupancy_schedule(self, hour):
        """Lịch chiếm dụng theo Fig.7 — weekday"""
        if   6  <= hour < 8:  return 0.25
        elif 8  <= hour < 12: return 1.0
        elif 12 <= hour < 13: return 0.5
        elif 13 <= hour < 17: return 1.0
        elif 17 <= hour < 20: return 0.5
        else: return 0.0

    def _add_gaussian_noise(self, x, std=0.1):
        """Eq.(10): nhiễu Gaussian mô phỏng bất định (std=0.1)"""
        return x * np.random.normal(1.0, std)

    def step(self, state, action):
        """
        state:  [hour, Toa, omega_oa, q_sol, C_CO2_oa, C_PM_oa,
                 Tza,  omega_za, C_CO2_za, C_PM_za]
        action: [T_chws_sp, D_oa, f_sa, P_air]  — normalized [0,1]
        Returns: next_state, reward, info
        """
        hour, Toa, omega_oa, q_sol, C_CO2_oa, C_PM_oa, \
            Tza, omega_za, C_CO2_za, C_PM_za = state

        T_chws_sp, D_oa, f_sa, P_air_raw = action
        P_air = 1 if P_air_raw > 0.5 else 0

        # ---- Denormalize action (Table 5) ----
        if 6 <= hour < 20:  # Daytime
            T_chws_sp = 5.0  + T_chws_sp * 10.0  # [5–15°C]
            D_oa      = 0.2  + D_oa      * 0.8   # [20–100%]
            f_sa      = 0.1  + f_sa      * 0.9   # [10–100%]
        else:               # Nighttime
            T_chws_sp = 15.0
            D_oa      = D_oa * 0.3
            f_sa      = 0.1

        # ---- HVAC airflow ----
        V_sa, V_oa, V_ra = self.hvac.calc_airflow(f_sa, D_oa)
        T_mix = (V_oa * Toa + V_ra * Tza) / (V_sa + 1e-6)
        omega_mix = (V_oa * omega_oa + V_ra * omega_za) / (V_sa + 1e-6)
        T_sa, omega_sa = self.hvac.calc_supply_air_state(T_mix, omega_mix, T_chws_sp)
        E_fan = self.hvac.calc_fan_power(f_sa)

        # ---- Tải nhiệt nội thất ----
        occ_frac = self._occupancy_schedule(hour)
        N_occ   = self._add_gaussian_noise(occ_frac * self.N_OCC_MAX, 0.1)
        Q_gain  = (self._add_gaussian_noise(Q_LIG := self.Q_LIG_MAX * occ_frac, 0.1)
                 + self._add_gaussian_noise(self.Q_EQP_MAX * occ_frac, 0.1)
                 + N_occ * self.Q_OCC_SEN)
        S_mois  = self._add_gaussian_noise(N_occ * self.S_OCC_MOIS, 0.05)
        S_co2   = self._add_gaussian_noise(N_occ * self.S_OCC_CO2, 0.05)

        # ---- Tính năng lượng chiller (ước tính đơn giản) ----
        Q_hvac_load = max(0, self.envelope.cp_a * self.envelope.rho_a
                         * V_sa * (Tza - T_sa))
        COP = 3.0  # giả sử COP = 3
        E_chiller  = Q_hvac_load / COP / 1000  # kW
        E_pump     = 0.05 * E_chiller           # ước tính ~5% chiller
        E_purifier = 0.042 if P_air else 0.0    # 42W (Section 4.4)
        E_total    = (E_chiller + E_pump + E_fan + E_purifier) * 900/3600  # kWh

        # ---- Cập nhật trạng thái ----
        Q_hvac_zone = self.envelope.calc_Q_hvac(V_sa, T_sa, Tza)
        Tza_new, self.Tw = self.envelope.step(
            Tza, self.Tw, Toa, q_sol, Q_hvac_zone, Q_gain)

        omega_za_new = self.humidity.step(omega_za, omega_sa, V_sa, S_mois)
        C_CO2_new    = self.co2.step(C_CO2_za, C_CO2_oa, V_oa, S_co2)
        C_PM_new     = self.pm25.step(C_PM_za, C_PM_oa, V_oa, V_ra, P_air)

        # ---- Relative humidity ----
        phi_za_new = self._omega_to_rh(omega_za_new, Tza_new)

        # ---- Reward (Eq.15–20) ----
        reward = self._calc_reward(
            E_total, Tza_new, phi_za_new, C_CO2_new, C_PM_new, hour)

        next_hour = (hour + 0.25) % 24
        next_state = [next_hour, Toa, omega_oa, q_sol,
                      C_CO2_oa, C_PM_oa,
                      Tza_new, omega_za_new, C_CO2_new, C_PM_new]

        info = {'E_kWh': E_total, 'T_sa': T_sa, 'V_sa': V_sa,
                'V_oa': V_oa, 'phi_za': phi_za_new}
        return np.array(next_state), reward, info

    def _omega_to_rh(self, omega, T):
        """Chuyển humidity ratio → relative humidity"""
        p_sat = 0.6112 * np.exp(17.67 * T / (T + 243.5))  # kPa
        rh = omega * 101.325 / (0.622 + omega) / p_sat
        return np.clip(rh, 0, 1)

    def _calc_reward(self, E, Tza, phi_za, C_CO2, C_PM, hour):
        """Eq.(15–20)"""
        a1, a2, a3, a4, a5 = self.ALPHA

        f_T   = max(0, Tza - self.T_U) + max(0, self.T_L - Tza)  # Eq.17
        f_phi = max(0, phi_za - self.PHI_U)                        # Eq.18
        f_co2 = 1.0 if C_CO2 >= 1000 else 0.0                     # Eq.19
        f_pm  = 1.0 if C_PM  >= 10   else 0.0                     # Eq.20

        if 6 <= hour < 20:  # Occupied
            r = -(a1*E + a2*f_T + a3*f_phi + a4*f_co2 + a5*f_pm)
        else:               # Unoccupied
            r = -a1 * E
        return r
