# drl/ou_noise.py
import numpy as np

class OUNoise:
    """
    Ornstein-Uhlenbeck process (Algorithm 1)
    theta = 0.15 (reversion rate), sigma = 0.2 (Table 6)
    """
    def __init__(self, action_dim: int, mu=0.0, theta=0.15, sigma=0.2):
        self.action_dim = action_dim
        self.mu    = mu
        self.theta = theta
        self.sigma = sigma
        self.reset()

    def reset(self):
        self.state = np.ones(self.action_dim) * self.mu

    def sample(self) -> np.ndarray:
        dx = (self.theta * (self.mu - self.state)
              + self.sigma * np.random.standard_normal(self.action_dim))
        self.state += dx
        return self.state.copy()
