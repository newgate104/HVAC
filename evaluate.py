# evaluate.py
import numpy as np
import matplotlib.pyplot as plt
from simulator.hybrid_sim import HybridSimulator
from drl.ddpg_agent       import DDPGAgent
from data.weather_gen     import SeoulWeatherGenerator

STATE_MIN = np.array([0,-5,0.002,0,390,0,15,0.003,400,0],  dtype=np.float32)
STATE_MAX = np.array([24,40,0.025,900,510,80,35,0.022,2000,50], dtype=np.float32)

def norm(s): return (np.array(s)-STATE_MIN)/(STATE_MAX-STATE_MIN+1e-8)
def ddpg2sim(a): return (np.clip(a,-1,1)+1)/2

def evaluate(use_trained: bool = True):
    sim     = HybridSimulator()
    agent   = DDPGAgent()
    weather = SeoulWeatherGenerator(seed=99)

    if use_trained:
        agent.load('checkpoints')
        label = 'DRL (trained)'
    else:
        label = 'Random policy'

    T_day, om_day, qs_day, pm_day = weather.generate_day(month=7)

    state = np.array([0.0, T_day[0], om_day[0], qs_day[0],
                      450.0, pm_day[0], 24.0, 0.010, 600.0, 5.0], dtype=np.float32)

    log = {k: [] for k in ['Tza','phi','CO2','PM','E','r',
                            'f_T','f_phi','f_co2','f_pm',
                            'act_Tchws','act_Doa','act_fsa','act_Pair']}

    for step in range(96):
        state[0] = step * 0.25
        state[1:6] = [T_day[step], om_day[step], qs_day[step], 450.0, pm_day[step]]

        if use_trained:
            a_ddpg = agent.select_action(norm(state), add_noise=False)
        else:
            a_ddpg = np.random.uniform(-1, 1, 4)

        a_sim = ddpg2sim(a_ddpg)
        next_s, reward, info = sim.step(state.tolist(), a_sim)
        next_s = np.array(next_s, dtype=np.float32)

        # Reward breakdown (Eq.15–20)
        Tza  = next_s[6]
        phi  = info['phi_za']
        CO2  = next_s[8]
        PM   = next_s[9]
        E    = info['E_kWh']
        f_T  = max(0, Tza-24.5) + max(0, 22-Tza)
        f_ph = max(0, phi-0.60)
        f_c  = 1.0 if CO2 >= 1000 else 0.0
        f_pm = 1.0 if PM  >= 10   else 0.0

        # Decode action về đơn vị thực
        T_chws = 5  + a_sim[0]*10
        D_oa   = 0.2+ a_sim[1]*0.8
        f_sa   = 0.1+ a_sim[2]*0.9

        for k,v in zip(log.keys(),
                       [Tza,phi,CO2,PM,E,reward,
                        f_T,f_ph,f_c,f_pm,
                        T_chws,D_oa,f_sa,a_sim[3]]):
            log[k].append(v)

        state = next_s

    # ---- In thống kê ----
    hours = np.arange(96)*0.25
    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")
    print(f"  Tza trung bình:    {np.mean(log['Tza']):.2f}°C  (max={np.max(log['Tza']):.2f})")
    print(f"  RH trung bình:     {np.mean(log['phi'])*100:.1f}%  (max={np.max(log['phi'])*100:.1f}%)")
    print(f"  CO2 trung bình:    {np.mean(log['CO2']):.0f} ppm")
    print(f"  PM2.5 trung bình:  {np.mean(log['PM']):.2f} μg/m³")
    print(f"  Tổng năng lượng:   {sum(log['E']):.3f} kWh/ngày")
    print(f"  Reward trung bình: {np.mean(log['r']):.3f}/step")
    print(f"\n  --- Vi phạm ---")
    print(f"  Temp violation %:  {100*np.mean([x>0 for x in log['f_T']]):.1f}%")
    print(f"  RH   violation %:  {100*np.mean([x>0 for x in log['f_phi']]):.1f}%")
    print(f"  CO2  violation %:  {100*np.mean([x>0 for x in log['f_co2']]):.1f}%")
    print(f"  PM   violation %:  {100*np.mean([x>0 for x in log['f_pm']]):.1f}%")
    print(f"\n  --- Action trung bình (daytime) ---")
    occ = [i for i in range(96) if 6<=i*0.25<20]
    print(f"  T_chws: {np.mean([log['act_Tchws'][i] for i in occ]):.2f}°C")
    print(f"  D_oa:   {np.mean([log['act_Doa'][i]   for i in occ])*100:.1f}%")
    print(f"  f_sa:   {np.mean([log['act_fsa'][i]   for i in occ])*100:.1f}%")
    print(f"  P_air ON%: {100*np.mean([log['act_Pair'][i] for i in occ]):.1f}%")

    # ---- Plot ----
    fig, axes = plt.subplots(4, 2, figsize=(14, 10))
    fig.suptitle(f'{label} — 1 ngày tháng 7 Seoul', fontsize=13)

    axes[0,0].plot(hours, log['Tza'], 'r'); axes[0,0].axhline(24.5,ls='--',c='gray')
    axes[0,0].axhline(22, ls='--', c='gray'); axes[0,0].set_title('Nhiệt độ (°C)')
    axes[0,0].set_ylabel('°C'); axes[0,0].fill_between(hours,[22]*96,[24.5]*96,alpha=0.1,color='green')

    axes[0,1].plot(hours, [x*100 for x in log['phi']], 'b')
    axes[0,1].axhline(60, ls='--', c='gray'); axes[0,1].set_title('Relative Humidity (%)')

    axes[1,0].plot(hours, log['CO2'], 'g'); axes[1,0].axhline(1000,ls='--',c='gray')
    axes[1,0].set_title('CO₂ (ppm)')

    axes[1,1].plot(hours, log['PM'], 'm'); axes[1,1].axhline(10,ls='--',c='gray')
    axes[1,1].set_title('PM2.5 (μg/m³)')

    axes[2,0].plot(hours, log['act_Tchws'], 'c'); axes[2,0].set_title('Action: T_chws (°C)')
    axes[2,1].plot(hours, [x*100 for x in log['act_Doa']], 'orange')
    axes[2,1].set_title('Action: Damper opening (%)')

    axes[3,0].plot(hours, [x*100 for x in log['act_fsa']], 'purple')
    axes[3,0].set_title('Action: Fan speed (%)')
    axes[3,1].plot(hours, log['r'], 'k'); axes[3,1].set_title('Reward/step')

    for ax in axes.flat: ax.set_xlabel('Hour'); ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(f'logs/eval_{"trained" if use_trained else "random"}.png', dpi=130)
    plt.show()


if __name__ == '__main__':
    evaluate(use_trained=True)   # agent đã train
    evaluate(use_trained=False)  # policy ngẫu nhiên để so sánh
