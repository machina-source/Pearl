from abc import ABC, abstractmethod

import gym
import numpy as np
import torch
import torch.nn.functional as F
from pearl.api.action import Action
from pearl.api.action_result import ActionResult
from pearl.api.action_space import ActionSpace
from pearl.api.environment import Environment
from pearl.api.observation import Observation
from pearl.utils.action_spaces import DiscreteActionSpace


class FixedNumberOfStepsEnvironment(Environment):
    def __init__(self, number_of_steps=100):
        self.number_of_steps_so_far = 0
        self.number_of_steps = number_of_steps
        self._action_space = DiscreteActionSpace([True, False])

    def step(self, action: Action) -> Observation:
        self.number_of_steps_so_far += 1
        return ActionResult(
            observation=self.number_of_steps_so_far,
            reward=self.number_of_steps_so_far,
            terminated=True,
            truncated=True,
            info={},
        )

    def render(self):
        print(self.number_of_steps_so_far)

    @property
    def action_space(self) -> ActionSpace:
        return self._action_space

    def reset(self):
        return self.number_of_steps_so_far, self.action_space

    def __str__(self):
        return type(self).__name__


class BoxObservationsEnvironmentBase(Environment, ABC):
    """
    An environment adapter mapping a Discrete observation space into a Box observation space with dimension 1.

    This is useful to use with agents expecting tensor observations.
    """

    def __init__(
        self,
        base_environment: Environment,
    ):
        self.base_environment = base_environment
        self.observation_space = self.make_observation_space(base_environment)

    @staticmethod
    @abstractmethod
    def make_observation_space(base_environment: Environment):
        pass

    @abstractmethod
    def compute_tensor_observation(self, observation):
        pass

    @property
    def action_space(self):
        return self.base_environment.action_space

    def step(self, action: Action) -> ActionResult:
        action_result = self.base_environment.step(action)
        action_result.observation = self.compute_tensor_observation(
            action_result.observation
        )
        return action_result

    def reset(self):
        observation, action_space = self.base_environment.reset()
        return self.compute_tensor_observation(observation), action_space

    def __str__(self):
        return f"{self.short_description} from {self.base_environment}"

    @property
    def short_description(self):
        return self.__class__.__name__


class BoxObservationsFromDiscrete(BoxObservationsEnvironmentBase):
    """
    An environment adapter mapping a Discrete observation space into a Box observation space with dimension 1.
    The observations are tensors of length 1 containing the original observations.

    This is useful to use with agents expecting tensor observations.
    """

    def __init__(self, base_environment: Environment):
        super(BoxObservationsFromDiscrete, self).__init__(base_environment)

    @staticmethod
    def make_observation_space(base_environment: Environment):
        low_action = np.array([0])
        high_action = np.array([base_environment.observation_space.n - 1])
        return gym.spaces.Box(low=low_action, high=high_action, shape=(1,))

    def compute_tensor_observation(self, observation):
        return torch.tensor([observation], dtype=torch.float32)


class OneHotObservationsFromDiscrete(BoxObservationsEnvironmentBase):
    """
    An environment adapter mapping a Discrete observation space into a Box observation space with dimension 1
    where the observation is a one-hot vector.

    This is useful to use with agents expecting tensor observations.
    """

    def __init__(self, base_environment: Environment):
        super(OneHotObservationsFromDiscrete, self).__init__(base_environment)

    @staticmethod
    def make_observation_space(base_environment: Environment):
        n = base_environment.observation_space.n
        low = np.full((n,), 0)
        high = np.full((n,), 1)
        return gym.spaces.Box(low=low, high=high, shape=(n,))

    def compute_tensor_observation(self, observation):
        if isinstance(observation, torch.Tensor):
            observation_tensor = observation
        else:
            observation_tensor = torch.tensor(observation)
        return F.one_hot(
            observation_tensor, self.base_environment.observation_space.n
        ).float()

    @property
    def short_description(self):
        return "One-hot observations"
