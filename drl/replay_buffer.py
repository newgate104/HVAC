# drl/replay_buffer.py
import numpy as np
from collections import deque
import random

class ReplayBuffer:
    """Replay buffer R theo Algorithm 1. Size = 1.5×10⁶ (Table 6)"""

    def __init__(self, max_size: int = 1_500_000):
        self.buffer = deque(maxlen=max_size)

    def store(self, state, action, reward, next_state):
        self.buffer.append((
            np.array(state,      dtype=np.float32),
            np.array(action,     dtype=np.float32),
            float(reward),
            np.array(next_state, dtype=np.float32),
        ))

    def sample(self, batch_size: int = 128):
        """Random mini-batch N=128 (Table 6)"""
        batch = random.sample(self.buffer, batch_size)
        s, a, r, s2 = zip(*batch)
        return (np.array(s,  dtype=np.float32),
                np.array(a,  dtype=np.float32),
                np.array(r,  dtype=np.float32).reshape(-1, 1),
                np.array(s2, dtype=np.float32))

    def __len__(self):
        return len(self.buffer)
