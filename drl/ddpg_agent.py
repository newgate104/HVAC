# drl/ddpg_agent_v2.py
"""
v2 — 4 fix so với v1:
  1. Gradient clipping (norm=1.0) cho cả actor và critic
  2. Warm-up: chỉ train sau khi buffer có >= WARMUP_SIZE samples
  3. Critic update 2× mỗi bước, actor update 1×  (giống TD3)
  4. Reward clipping [-20, 0] trước khi lưu vào buffer
"""
import os
import numpy as np
import tensorflow as tf
from .networks      import build_actor, build_critic
from .replay_buffer import ReplayBuffer
from .ou_noise      import OUNoise

WARMUP_SIZE = 10_000   # số samples tối thiểu trước khi train
GRAD_NORM   = 1.0      # gradient clip norm
CRITIC_FREQ = 2        # critic update mỗi bước
ACTOR_FREQ  = 1        # actor update mỗi CRITIC_FREQ bước

class DDPGAgentV2:
    def __init__(self, state_dim=10, action_dim=4):
        self.state_dim  = state_dim
        self.action_dim = action_dim

        # Hyperparameters (Table 6)
        self.gamma      = 0.98
        self.tau        = 0.005
        self.lr_critic  = 5e-5
        self.lr_actor   = 2.5e-5
        self.batch_size = 128
        self._step_count = 0  # đếm số lần train_step được gọi

        # Networks
        self.actor         = build_actor(state_dim, action_dim)
        self.target_actor  = build_actor(state_dim, action_dim)
        self.critic        = build_critic(state_dim, action_dim)
        self.target_critic = build_critic(state_dim, action_dim)
        self.target_actor.set_weights(self.actor.get_weights())
        self.target_critic.set_weights(self.critic.get_weights())

        self.actor_opt  = tf.keras.optimizers.Adam(self.lr_actor)
        self.critic_opt = tf.keras.optimizers.Adam(self.lr_critic)

        self.replay_buffer = ReplayBuffer(max_size=1_500_000)
        self.noise = OUNoise(action_dim, theta=0.15, sigma=0.2)

    # ------------------------------------------------------------------
    def select_action(self, state, add_noise=True):
        s = tf.constant([state], dtype=tf.float32)
        a = self.actor(s, training=False).numpy()[0]
        if add_noise:
            a += self.noise.sample()
        return np.clip(a, -1.0, 1.0)

    # ------------------------------------------------------------------
    @tf.function
    def _update_critic(self, s, a, r, s2):
        a2    = self.target_actor(s2, training=False)
        q2    = self.target_critic([s2, a2], training=False)
        y     = r + self.gamma * q2
        with tf.GradientTape() as tape:
            q_pred = self.critic([s, a], training=True)
            loss   = tf.reduce_mean(tf.square(y - q_pred))
        grads = tape.gradient(loss, self.critic.trainable_variables)
        # FIX 1: gradient clipping
        grads, _ = tf.clip_by_global_norm(grads, GRAD_NORM)
        self.critic_opt.apply_gradients(zip(grads, self.critic.trainable_variables))
        return loss

    @tf.function
    def _update_actor(self, s):
        with tf.GradientTape() as tape:
            a_pred = self.actor(s, training=True)
            q_val  = self.critic([s, a_pred], training=False)
            loss   = -tf.reduce_mean(q_val)
        grads = tape.gradient(loss, self.actor.trainable_variables)
        # FIX 1: gradient clipping
        grads, _ = tf.clip_by_global_norm(grads, GRAD_NORM)
        self.actor_opt.apply_gradients(zip(grads, self.actor.trainable_variables))
        return loss

    @tf.function
    def _soft_update(self):
        for t, w in zip(self.target_critic.trainable_variables,
                        self.critic.trainable_variables):
            t.assign(self.tau * w + (1 - self.tau) * t)
        for t, w in zip(self.target_actor.trainable_variables,
                        self.actor.trainable_variables):
            t.assign(self.tau * w + (1 - self.tau) * t)

    # ------------------------------------------------------------------
    def store(self, s, a, r, s2):
        """FIX 4: clip reward trước khi lưu"""
        r_clipped = np.clip(r, -20.0, 0.0)
        self.replay_buffer.store(s, a, r_clipped, s2)

    def train_step(self):
        # FIX 2: warm-up — chưa đủ sample thì bỏ qua
        if len(self.replay_buffer) < WARMUP_SIZE:
            return None, None

        self._step_count += 1
        s, a, r, s2 = self.replay_buffer.sample(self.batch_size)
        s  = tf.constant(s,  dtype=tf.float32)
        a  = tf.constant(a,  dtype=tf.float32)
        r  = tf.constant(r,  dtype=tf.float32)
        s2 = tf.constant(s2, dtype=tf.float32)

        c_loss = None
        a_loss = None

        # FIX 3: critic update 2× mỗi bước
        for _ in range(CRITIC_FREQ):
            c_loss = self._update_critic(s, a, r, s2)

        # FIX 3: actor update 1× mỗi CRITIC_FREQ bước
        if self._step_count % CRITIC_FREQ == 0:
            a_loss = self._update_actor(s)
            self._soft_update()

        return (float(c_loss) if c_loss is not None else None,
                float(a_loss) if a_loss is not None else None)

    # ------------------------------------------------------------------
    def save(self, path='checkpoints_v2'):
        os.makedirs(path, exist_ok=True)
        self.actor.save_weights(f'{path}/actor.weights.h5')
        self.critic.save_weights(f'{path}/critic.weights.h5')
        print(f"  [Saved v2] → {path}/")

    def load(self, path='checkpoints_v2'):
        self.actor.load_weights(f'{path}/actor.weights.h5')
        self.critic.load_weights(f'{path}/critic.weights.h5')
        self.target_actor.set_weights(self.actor.get_weights())
        self.target_critic.set_weights(self.critic.get_weights())
        print(f"  [Loaded v2] ← {path}/")
