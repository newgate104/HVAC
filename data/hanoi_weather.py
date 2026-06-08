# data/hanoi_weather_loader.py
"""
Load dữ liệu TMYx Hà Đông từ EPW file.
Thay thế SeoulWeatherGenerator.

EPW format (EnergyPlus Weather):
  col[6]  DryBulb_C           → T_oa
  col[7]  DewPoint_C          → omega_oa (qua công thức psychrometric)
  col[8]  RelHum_pct          → kiểm tra chéo
  col[9]  AtmPressure_Pa      → dùng trong tính omega
  col[13] GlobHorizRad_Wm2    → q_sol
"""
import math
import zipfile
import numpy as np
from pathlib import Path

class HanoiWeatherLoader:
    """
    Load dữ liệu TMYx Hà Đông từ file EPW.
    Cung cấp daily profiles (96 timesteps × 15min) cho simulator.
    """

    # Tháng simulate (Section 3.3.5: May–Oct, không có heating)
    SUMMER_MONTHS = [5, 6, 7, 8, 9, 10]

    def __init__(self, epw_path: str, noise_std: float = 0.02):
        """
        epw_path : đường dẫn tới .epw hoặc .zip chứa .epw
        noise_std: std của Gaussian noise thêm vào để augment (Eq.10 bài báo)
        """
        self.noise_std = noise_std
        self._data = self._load_epw(epw_path)
        self._build_daily_index()
        summer_n = len([r for r in self._data if r['month'] in self.SUMMER_MONTHS])
        print(f"[HanoiWeather] Loaded {len(self._data)} hourly rows "
              f"| Summer rows: {summer_n}")

    # ── EPW parser ────────────────────────────────────────────────────
    def _load_epw(self, path: str) -> list:
        """Đọc EPW từ file hoặc zip, trả về list of dicts."""
        path = Path(path)
        if path.suffix == '.zip':
            with zipfile.ZipFile(path) as zf:
                epw_name = next(n for n in zf.namelist() if n.endswith('.epw'))
                content = zf.read(epw_name).decode('utf-8', errors='replace')
        else:
            content = path.read_text(encoding='utf-8', errors='replace')

        rows = []
        for line in content.splitlines()[8:]:   # bỏ 8 dòng header
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) < 35:
                continue
            try:
                rows.append({
                    'month':  int(parts[1]),
                    'day':    int(parts[2]),
                    'hour':   int(parts[3]) - 1,    # EPW: 1-24 → 0-23
                    'T_oa':   float(parts[6]),      # °C
                    'T_dp':   float(parts[7]),
                    'rh_oa':  float(parts[8]),      # %
                    'P_atm':  float(parts[9]),      # Pa
                    'q_sol':  max(0.0, float(parts[13])),  # W/m² GHI
                    'omega_oa': self._dp_to_omega(T_dp, P_atm),
                })
            except (ValueError, IndexError):
                continue
        return rows

    @staticmethod
    def _dp_to_omega(T_dp: float, P_atm: float) -> float:
        """
        Dew point → humidity ratio  (ASHRAE Fundamentals psychrometrics)
        p_sat(T_dp) = 611.2 · exp(17.67·T/(T+243.5))  [Pa]
        omega = 0.622 · p_sat / (P_atm - p_sat)        [kg/kg]
        """
        p_sat = 611.2 * math.exp(17.67 * T_dp / (T_dp + 243.5))
        p_sat = min(p_sat, P_atm * 0.99)   # tránh chia 0
        return float(np.clip(0.622 * p_sat / (P_atm - p_sat), 0.001, 0.035))

    # ── Xây index theo ngày ───────────────────────────────────────────
    def _build_daily_index(self):
        """Group hourly rows → {(month, day): [24 rows]}"""
        self._daily: dict = {}
        for row in self._data:
            key = (row['month'], row['day'])
            self._daily.setdefault(key, []).append(row)

        # Chỉ giữ ngày đủ 24 giờ
        self._summer_days = [
            (m, d) for (m, d), hrs in self._daily.items()
            if m in self.SUMMER_MONTHS and len(hrs) == 24
        ]
        self._summer_days.sort()
        print(f"[HanoiWeather] Summer days: {len(self._summer_days)} "
              f"({len(self._summer_days)/30:.0f} tháng × 30 ngày)")

    # ── PM2.5 Hà Nội ─────────────────────────────────────────────────
    def _generate_pm25(self, month: int) -> np.ndarray:
        """
        PM2.5 outdoor Hà Nội tháng 5-10 [μg/m³]
        Seoul (paper): lognormal(2.7, 0.65) → mean ≈ 18 μg/m³
        Hà Nội mùa hè: trung bình 20-30 μg/m³ (IQAir VN historical)
            lognormal(mu, 0.55):
              tháng 5 → mu=3.22 → mean≈27, tháng 7 → mu=2.89 → mean≈20
        """
        monthly_mu = {5: 3.22, 6: 3.00, 7: 2.89, 8: 3.00, 9: 3.09, 10: 3.40}
        mu        = monthly_mu.get(month, 3.10)
        base      = float(np.clip(np.random.lognormal(mu, 0.55), 1.0, 150.0))
        noise     = np.random.normal(0, 2.0, 96)
        return np.clip(np.ones(96) * base + noise, 0.0, 150.0)

    # ── API chính (thay thế SeoulWeatherGenerator.generate_day) ──────
    def generate_day(self, month: int, day: int = None, add_noise: bool = True):
        """
        Trả về 4 arrays shape (96,) — khớp với SeoulWeatherGenerator:
            T_oa    [°C]       outdoor dry bulb temperature
            omega_oa [kg/kg]   outdoor humidity ratio  (tính từ dew point)
            q_sol   [W/m²]     global horizontal irradiance
            C_PM_oa [μg/m³]    outdoor PM2.5  ← Hanoi statistics

        Nội suy từ 24h hourly → 96 timestep × 15min.
        Gaussian noise theo Eq.(10) bài báo: x ← x·φ, φ~N(1,noise_std²)

        """
        # Chọn ngày
        candidates = [(m, d) for (m, d) in self._summer_days if m == month]
        if not candidates:
            raise ValueError(f"Không có dữ liệu tháng {month}")
        if day is None:
            m, d = candidates[np.random.randint(len(candidates))]
        else:
            m, d = month, day

        hrs = sorted(self._daily[(m, d)], key=lambda r: r['hour'])

        # Nội suy từ 24 giờ → 96 timesteps (15min)
        T_h    = np.array([r['T_oa']    for r in hrs])
        om_h   = np.array([r['omega_oa'] for r in hrs])
        qs_h   = np.array([r['q_sol']   for r in hrs])
        rh_h   = np.array([r['rh_oa']   for r in hrs])

        t24 = np.arange(24)
        t96 = np.linspace(0, 23, 96)

        T_96  = np.interp(t96, t24, T_h)
        om_96 = np.interp(t96, t24, om_h)
        qs_96 = np.interp(t96, t24, qs_h)
        rh_96 = np.interp(t96, t24, rh_h)

        # Thêm Gaussian noise (Eq.10: φ ~ N(1, 0.1²))
        if add_noise:
            phi = np.random.normal(1.0, self.noise_std, 96)
            T_96  = T_96  * np.random.normal(1.0, 0.01, 96) + np.random.normal(0, 0.3, 96)
            om_96 = np.clip(om_96 * phi, 0.005, 0.035)
            qs_96 = np.clip(qs_96 * np.abs(phi), 0, 1100)
        C_PM_96 = self._generate_pm25(month)

        return T_96, om_96, qs_96, C_PM_96

    def get_months(self) -> list:
        return self.SUMMER_MONTHS

    # ── Thống kê ──────────────────────────────────────────────────────
    def summary(self):
        print("\n=== Thống kê Hà Đông EPW (mùa hè tháng 5–10) ===")
        print(f"{'Tháng':>6} | {'T_min':>6} {'T_mean':>7} {'T_max':>6} "
              f"| {'RH_mean':>8} | {'omega_mean':>10} | {'GHI_max':>8}")
        print("-" * 65)
        for m in self.SUMMER_MONTHS:
            rows = [r for r in self._data if r['month'] == m]
            T = [r['T_oa']    for r in rows]
            rh= [r['rh_oa']   for r in rows]
            om= [r['omega_oa'] for r in rows]
            qs= [r['q_sol']   for r in rows]
            print(f"  {m:>4} | {min(T):>6.1f} {np.mean(T):>7.2f} {max(T):>6.1f} "
                  f"| {np.mean(rh):>7.1f}% | {np.mean(om):>10.4f} "
                  f"| {max(qs):>7.0f}W")
