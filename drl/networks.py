# drl/networks.py
import tensorflow as tf
from tensorflow import keras

def build_actor(state_dim: int = 10, action_dim: int = 4) -> keras.Model:
    """
    Actor: s_t → a_t  (Fig.9)
    Kiến trúc: Input → z1(256,relu) → z2(256,relu) → Output(tanh)
    """
    inputs  = keras.Input(shape=(state_dim,), name='state')
    z1      = keras.layers.Dense(256, activation='relu', name='z1')(inputs)
    z2      = keras.layers.Dense(256, activation='relu', name='z2')(z1)
    outputs = keras.layers.Dense(action_dim, activation='tanh', name='action')(z2)
    return keras.Model(inputs, outputs, name='actor')


def build_critic(state_dim: int = 10, action_dim: int = 4) -> keras.Model:
    """
    Critic: (s_t, a_t) → Q(s,a)  (Fig.10)
    Kiến trúc:
        s → z1(16,relu) → z2(32,relu) ─┐
                                         Concat → z4(256,relu) → z5(256,relu) → Q
        a → z3(32,relu) ────────────────┘
    """
    # State branch
    s_in = keras.Input(shape=(state_dim,),  name='state')
    z1   = keras.layers.Dense(16,  activation='relu', name='z1')(s_in)
    z2   = keras.layers.Dense(32,  activation='relu', name='z2')(z1)

    # Action branch
    a_in = keras.Input(shape=(action_dim,), name='action')
    z3   = keras.layers.Dense(32,  activation='relu', name='z3')(a_in)

    # Merge
    merged = keras.layers.Concatenate(name='merge')([z2, z3])
    z4     = keras.layers.Dense(256, activation='relu', name='z4')(merged)
    z5     = keras.layers.Dense(256, activation='relu', name='z5')(z4)
    q_out  = keras.layers.Dense(1,   name='Q')(z5)

    return keras.Model([s_in, a_in], q_out, name='critic')
