# train.py
import os
import numpy as np
import matplotlib.pyplot as plt

from simulator.hybrid_sim import HybridSimulator
from drl.ddpg_agent       import DDPGAgent
from data.weather_gen     import SeoulWeatherGenerator

# ---- Normalization ranges (state vector) ----
STATE_MIN = np.array([0,  -5, 0.002,   0, 390,  0, 15, 0.003,  400,  0], dtype=np.float32)
STATE_MAX = np.array([24,  40, 0.025, 900, 510, 80, 35, 0.022, 2000, 50], dtype=np.float32)

def norm(state: np.ndarray) -> np.ndarray:
    return (state - STATE_MIN) / (STATE_MAX - STATE_MIN + 1e-8)

def ddpg_to_sim_action(a_ddpg: np.ndarray) -> np.ndarray:
    """DDPG output [-1,1] → simulator input [0,1]"""
    return (a_ddpg + 1.0) / 2.0


def run_episode(sim, agent, weather, months, train=True):
    """Chạy 1 episode = 6 tháng × 30 ngày × 96 bước"""
    total_reward = 0.0
    total_steps  = 0

    for month in months:
        for _ in range(30):
            T_day, om_day, qs_day, pm_day = weather.generate_day(month)

            # Reset trạng thái đầu ngày
            state = np.array([0.0, T_day[0], om_day[0], qs_day[0],
                               450.0, pm_day[0],
                               24.0, 0.010, 600.0, 5.0], dtype=np.float32)

            for step in range(96):
                # Cập nhật điều kiện ngoài trời theo thời điểm trong ngày
                state[0] = step * 0.25
                state[1] = T_day[step]
                state[2] = om_day[step]
                state[3] = qs_day[step]
                state[5] = pm_day[step]

                s_norm = norm(state)
                a_ddpg = agent.select_action(s_norm, add_noise=train)
                a_sim  = ddpg_to_sim_action(a_ddpg)

                next_state, reward, info = sim.step(state.tolist(), a_sim)
                next_state = np.array(next_state, dtype=np.float32)

                if train:
                    agent.replay_buffer.store(
                        s_norm, a_ddpg, reward, norm(next_state))
                    agent.train_step()

                state = next_state
                total_reward += reward
                total_steps  += 1

    return total_reward / total_steps   # reward trung bình/bước


def main():
    os.makedirs('checkpoints', exist_ok=True)
    os.makedirs('logs',        exist_ok=True)

    sim     = HybridSimulator()
    agent   = DDPGAgent(state_dim=10, action_dim=4)
    weather = SeoulWeatherGenerator(seed=42)

    N_EPISODES = 100        # 50 ep đủ hội tụ (Section 4.3); 100 cho chắc
    MONTHS     = [5,6,7,8,9,10]

    history = {'reward': [], 'episode': []}

    print(f"{'Episode':>8} | {'Avg Reward':>12} | {'Buffer':>10}")
    print("-" * 40)

    for ep in range(1, N_EPISODES + 1):
        agent.noise.reset()
        avg_r = run_episode(sim, agent, weather, MONTHS, train=True)

        history['reward'].append(avg_r)
        history['episode'].append(ep)

        if ep % 5 == 0:
            agent.save('checkpoints')
            print(f"{ep:>8} | {avg_r:>12.4f} | {len(agent.replay_buffer):>10,}")

    # ---- Vẽ learning curve (tương tự Fig.16) ----
    plt.figure(figsize=(9, 4))
    plt.plot(history['episode'], history['reward'], color='steelblue')
    plt.xlabel('Episode')
    plt.ylabel('Avg Reward / step')
    plt.title('DDPG Training Curve (Fig.16 replication)')
    plt.grid(True, alpha=0.4)
    plt.tight_layout()
    plt.savefig('logs/training_curve.png', dpi=150)
    plt.show()
    print("\nDone. Checkpoint → checkpoints/ | Curve → logs/training_curve.png")


if __name__ == '__main__':
    main()
