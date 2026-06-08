# train_v3.py
"""
Thay đổi so với train_v2.py:
  FIX 1: MONTHS scoping bug — truyền months làm tham số run_episode()
  FIX 2: STATE_MAX cập nhật cho Hà Nội (PM2.5 max 150, T_oa max 40)
  FIX 3: Dùng HanoiWeatherLoader thay SeoulWeatherGenerator
  FIX 4: Setpoint Hà Nội 26°C (từ PMV với clo=0.5)
"""
import os
import numpy as np
import matplotlib.pyplot as plt

from simulator.hybrid_sim import HybridSimulator
from drl.ddpg_agent       import DDPGAgentV2
from data.hanoi_weather   import HanoiWeatherLoader
#from data.weather_gen     import SeoulWeatherGenerator

STATE_MIN = np.array([0,-5,0.002,0,390,0,15,0.003,400,0], dtype=np.float32)
STATE_MAX = np.array([24,40,0.025,900,510,150,35,0.022,2000,50], dtype=np.float32)

def norm(s):
    return (np.array(s, dtype=np.float32)-STATE_MIN)/(STATE_MAX-STATE_MIN+1e-8)
def ddpg2sim(a):
    return (np.clip(a,-1,1)+1)/2

def run_episode(sim, agent, weather, months, train=True):
    total_r, steps = 0.0, 0
    for month in months:
        for _ in range(30):
            T_d, om_d, qs_d, pm_d = weather.generate_day(month)
            state = np.array([0,T_d[0],om_d[0],qs_d[0],450,pm_d[0],24,0.010,600,5],
                             dtype=np.float32)
            for step in range(96):
                state[0]=step*0.25
                state[1]=T_d[step]
                state[2]=om_d[step]
                state[3]=qs_d[step]
                state[5]=pm_d[step]

                sn     = norm(state)
                a_ddpg = agent.select_action(sn, add_noise=train)
                a_sim  = ddpg2sim(a_ddpg)

                next_s, reward, _ = sim.step(state.tolist(), a_sim)
                next_s = np.array(next_s, dtype=np.float32)

                if train:
                    agent.store(sn, a_ddpg, reward, norm(next_s))
                    agent.train_step()

                state = next_s
                total_r += reward
                steps += 1
    return total_r / steps

def main():
    os.makedirs('checkpoints_hanoi', exist_ok=True)
    os.makedirs('logs', exist_ok=True)

    sim     = HybridSimulator()
    agent   = DDPGAgentV2()
    weather = HanoiWeatherLoader(                             # SỬA 2
                  epw_path="data/VNM_NVN_Ha.Dong.488250_TMYx.epw",
                  noise_std=0.02)
#    weather = SeoulWeatherGenerator(seed=42)

    months  = weather.get_months()          # [5,6,7,8,9,10]

    N_EPISODES = 150
    rewards = []
    print(f"{'Episode':>8} | {'Avg R/step':>11} | {'Buffer':>10} | {'Status':>12}")
    print("-" * 55)

    for ep in range(1, N_EPISODES+1):
        agent.noise.reset()
        avg_r = run_episode(sim, agent, weather, months, train=True)
        rewards.append(avg_r)

        buf = len(agent.replay_buffer)
        status = "warming up" if buf < 200_000 else "training"

        if ep % 5 == 0:
            agent.save('checkpoints_hanoi')
            print(f"{ep:>8} | {avg_r:>11.4f} | {buf:>10,} | {status:>12}")

    # Plot
    fig, ax = plt.subplots(figsize=(9,4))
    ax.plot(rewards, color='steelblue', label='Hà Nội EPW (v3)')
    ax.axhline(-13.5, ls='--', c='red', alpha=0.6, label='v1 baseline (~−13.5)')
    ax.set_xlabel('Episode'); ax.set_ylabel('Avg Reward / step')
    ax.set_title('DDPG Training — Hà Nội Weather (TMYx)')
    ax.legend(); ax.grid(alpha=0.4)
    plt.tight_layout()
    plt.savefig('logs/training_curve_hanoi.png', dpi=150)
    plt.show()
    print("\nDone → checkpoints_hanoi/ | logs/training_curve_hanoi.png")

if __name__ == '__main__':
    main()
