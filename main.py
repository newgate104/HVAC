# main.py
import numpy as np
from simulator.hybrid_sim import HybridSimulator

sim = HybridSimulator()

# Trạng thái ban đầu (8h sáng, Seoul tháng 7)
state = [8.0,   # hour
         30.0,  # Toa [°C]
         0.018, # omega_oa [kg/kg]
         400.0, # q_sol [W/m²]
         450.0, # C_CO2_oa [ppm]
         15.0,  # C_PM_oa [μg/m³]
         24.0,  # Tza [°C]
         0.010, # omega_za [kg/kg]
         700.0, # C_CO2_za [ppm]
         5.0]   # C_PM_za [μg/m³]

# Action: T_chws_sp=0.2→7°C, D_oa=0.3, f_sa=0.2, P_air=OFF
action = [0.2, 0.3, 0.2, 0.0]

next_state, reward, info = sim.step(state, action)
print(f"Tza: {next_state[6]:.2f}°C | CO2: {next_state[8]:.0f}ppm | "
      f"PM2.5: {next_state[9]:.2f}μg/m³ | Reward: {reward:.3f}")
print(f"Energy: {info['E_kWh']:.4f} kWh | V_sa: {info['V_sa']:.3f} m³/s")
