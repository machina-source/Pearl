#!/usr/bin/env python3
# Copyright (c) Facebook, Inc. and its affiliates. All rights reserved.

from typing import Any, Dict

import torch

from pearl.api.action import Action
from pearl.core.common.history_summarization_modules.history_summarization_module import (
    SubjectiveState,
)
from pearl.core.common.neural_networks.utils import ensemble_forward
from pearl.core.common.policy_learners.exploration_module.exploration_module import (
    ExplorationModule,
)
from pearl.core.common.replay_buffer.transition import TransitionBatch
from pearl.core.contextual_bandits.policy_learners.contextual_bandit_base import (
    ContextualBanditBase,
)
from pearl.utils.action_spaces import DiscreteActionSpace
from pearl.utils.device import get_pearl_device
from pearl.utils.linear_regression import LinearRegression


class DisjointLinearBandit(ContextualBanditBase):
    """
    LinearBandit for discrete action space with each action has its own linear regression
    """

    def __init__(
        self,
        feature_dim: int,
        action_space: DiscreteActionSpace,
        exploration_module: ExplorationModule,
        training_rounds: int = 100,
        batch_size: int = 128,
    ) -> None:
        super(DisjointLinearBandit, self).__init__(
            feature_dim=feature_dim,
            training_rounds=training_rounds,
            batch_size=batch_size,
            exploration_module=exploration_module,
        )
        self.device = get_pearl_device()
        # Currently our disjoint LinUCB usecase only use LinearRegression
        self._linear_regressions = torch.nn.ModuleList(
            [LinearRegression(feature_dim=feature_dim) for _ in range(action_space.n)]
        ).to(self.device)
        self._discrete_action_space = action_space

    def learn_batch(self, batch: TransitionBatch) -> Dict[str, Any]:
        """
        Assumption of input is that action in batch is action idx instead of action value
        Only discrete action problem will use DisjointLinearBandit
        """

        for action_idx, linear_regression in enumerate(self._linear_regressions):
            index = torch.nonzero(batch.action == action_idx, as_tuple=True)[0]
            if index.numel() == 0:
                continue
            state = torch.index_select(
                batch.state,
                dim=0,
                index=index,
            )
            # cat state with corresponding action tensor
            expanded_action = (
                torch.Tensor(self._discrete_action_space[action_idx])
                .unsqueeze(0)
                .expand(state.shape[0], -1)
                .to(self.device)
            )
            context = torch.cat([state, expanded_action], dim=1)
            reward = torch.index_select(
                batch.reward,
                dim=0,
                index=index,
            )
            if batch.weight is not None:
                weight = torch.index_select(
                    batch.weight,
                    dim=0,
                    index=index,
                )
            else:
                weight = torch.ones(reward.shape, device=self.device)
            linear_regression.learn_batch(
                x=context,
                y=reward,
                weight=weight,
            )

        return {}

    def act(
        self,
        subjective_state: SubjectiveState,
        action_space: DiscreteActionSpace,
        _exploit: bool = False,
    ) -> Action:
        # TODO static discrete action space only, so here action_space should == self._discrete_action_space
        feature = self._discrete_action_space.cat_state_tensor(
            subjective_state=subjective_state
        )  # batch_size, action_count, feature_size

        values = ensemble_forward(self._linear_regressions, feature)

        return self._exploration_module.act(
            subjective_state=feature,
            action_space=action_space,
            values=values,
            representation=self._linear_regressions,
        )

    def get_scores(
        self,
        subjective_state: SubjectiveState,
    ) -> torch.Tensor:
        raise NotImplementedError("Implement when necessary")