# drl/ddpg_agent.py
import os
import numpy as np
import tensorflow as tf
from .networks      import build_actor, build_critic
from .replay_buffer import ReplayBuffer
from .ou_noise      import OUNoise

class DDPGAgent:
    """
    Deep Deterministic Policy Gradient — Algorithm 1 của bài báo.
    Hyperparameters: Table 6.
    """

    def __init__(self, state_dim: int = 10, action_dim: int = 4):
        self.state_dim  = state_dim
        self.action_dim = action_dim

        # ---- Hyperparameters (Table 6) ----
        self.gamma      = 0.98      # discount factor
        self.tau        = 0.005     # soft update rate τ
        self.lr_critic  = 5e-5
        self.lr_actor   = 2.5e-5
        self.batch_size = 128

        # ---- Networks (online + target) ----
        self.actor         = build_actor(state_dim, action_dim)
        self.target_actor  = build_actor(state_dim, action_dim)
        self.critic        = build_critic(state_dim, action_dim)
        self.target_critic = build_critic(state_dim, action_dim)

        # Khởi tạo target = online (Algorithm 1: θ'← θ)
        self.target_actor.set_weights(self.actor.get_weights())
        self.target_critic.set_weights(self.critic.get_weights())

        # ---- Adam optimizer (ref [56]) ----
        self.actor_opt  = tf.keras.optimizers.Adam(self.lr_actor)
        self.critic_opt = tf.keras.optimizers.Adam(self.lr_critic)

        # ---- Replay buffer & noise ----
        self.replay_buffer = ReplayBuffer(max_size=1_500_000)
        self.noise = OUNoise(action_dim, theta=0.15, sigma=0.2)

    # ------------------------------------------------------------------
    def select_action(self, state: np.ndarray, add_noise: bool = True) -> np.ndarray:
        """a_t = π(s_t|θ^π) + N_t  (Algorithm 1)"""
        s = tf.convert_to_tensor([state], dtype=tf.float32)
        a = self.actor(s, training=False).numpy()[0]
        if add_noise:
            a += self.noise.sample()
        return np.clip(a, -1.0, 1.0)

    # ------------------------------------------------------------------
    @tf.function
    def _update_critic(self, s, a, r, s2):
        """
        y_i = r_i + γ·Q'(s_{i+1}, π'(s_{i+1}|θ'^π)|θ'^Q)
        L   = (1/N) Σ (y_i - Q(s_i,a_i))²
        """
        a2  = self.target_actor(s2, training=False)
        q2  = self.target_critic([s2, a2], training=False)
        y   = r + self.gamma * q2

        with tf.GradientTape() as tape:
            q_pred = self.critic([s, a], training=True)
            loss   = tf.reduce_mean(tf.square(y - q_pred))

        grads = tape.gradient(loss, self.critic.trainable_variables)
        self.critic_opt.apply_gradients(zip(grads, self.critic.trainable_variables))
        return loss

    @tf.function
    def _update_actor(self, s):
        """
        ∇J ≈ (1/N) Σ ∇_a Q(s,a)|_{a=π(s)} · ∇_{θ^π} π(s|θ^π)
        """
        with tf.GradientTape() as tape:
            a_pred = self.actor(s, training=True)
            q_val  = self.critic([s, a_pred], training=False)
            loss   = -tf.reduce_mean(q_val)   # gradient ascent

        grads = tape.gradient(loss, self.actor.trainable_variables)
        self.actor_opt.apply_gradients(zip(grads, self.actor.trainable_variables))
        return loss

    @tf.function
    def _soft_update(self):
        """θ' ← τθ + (1-τ)θ'  (Algorithm 1)"""
        for t_w, w in zip(self.target_critic.trainable_variables,
                          self.critic.trainable_variables):
            t_w.assign(self.tau * w + (1 - self.tau) * t_w)
        for t_w, w in zip(self.target_actor.trainable_variables,
                          self.actor.trainable_variables):
            t_w.assign(self.tau * w + (1 - self.tau) * t_w)

    # ------------------------------------------------------------------
    def train_step(self):
        """1 mini-batch update. Trả về (critic_loss, actor_loss) hoặc (None,None)"""
        if len(self.replay_buffer) < self.batch_size:
            return None, None

        s, a, r, s2 = self.replay_buffer.sample(self.batch_size)
        s   = tf.constant(s,  dtype=tf.float32)
        a   = tf.constant(a,  dtype=tf.float32)
        r   = tf.constant(r,  dtype=tf.float32)
        s2  = tf.constant(s2, dtype=tf.float32)

        c_loss = self._update_critic(s, a, r, s2)
        a_loss = self._update_actor(s)
        self._soft_update()

        return float(c_loss), float(a_loss)

    # ------------------------------------------------------------------
    def save(self, path: str = 'checkpoints'):
        os.makedirs(path, exist_ok=True)
        self.actor.save_weights(f'{path}/actor.weights.h5')
        self.critic.save_weights(f'{path}/critic.weights.h5')
        print(f"  [Saved] → {path}/")

    def load(self, path: str = 'checkpoints'):
        self.actor.load_weights(f'{path}/actor.weights.h5')
        self.critic.load_weights(f'{path}/critic.weights.h5')
        self.target_actor.set_weights(self.actor.get_weights())
        self.target_critic.set_weights(self.critic.get_weights())
        print(f"  [Loaded] ← {path}/")
