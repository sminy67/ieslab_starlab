import copy

import torch

import models.configs as configs

from os.path import join as pjoin

from torch import nn
from torch.nn.modules.utils import _pair
import torch.nn.functional as F
from tt_mlp import TTLinear

class TTBlock(nn.Module):
    def __init__(self, hidden_shape, ff_shape, config):
        super(TTBlock, self).__init__()
        self.tt_fc0 = TTLinear(hidden_shape, ff_shape, config.tt_ranks, bias=True)
        self.tt_fc1 = TTLinear(ff_shape, hidden_shape, config.tt_ranks, bias=True)
        self.act_fn = nn.GELU()
        
    def forward(self, x):
        x = self.tt_fc0(x)
        x = self.act_fn(x)
        x = self.tt_fc1(x)
        return x

class MlpBlock(nn.Module):
    def __init__(self, hidden_dim, ff_dim):
        super(MlpBlock, self).__init__()
        self.fc0 = nn.Linear(hidden_dim, ff_dim, bias=True)
        self.fc1 = nn.Linear(ff_dim, hidden_dim, bias=True)
        self.act_fn = nn.GELU()

    def forward(self, x):
        x = self.fc0(x)
        x = self.act_fn(x)
        x = self.fc1(x)
        return x

class TTMixerBlock(nn.Module):
    def __init__(self, config):
        super(TTMixerBlock, self).__init__()
        self.token_mlp_block = MlpBlock(config.n_patches, config.tokens_mlp_dim)
        self.channel_mlp_block = TTBlock(config.hidden_shape, config.channels_mlp_shape, config)
        self.pre_norm = nn.LayerNorm(config.hidden_dim, eps=1e-6)
        self.post_norm = nn.LayerNorm(config.hidden_dim, eps=1e-6)

    def forward(self, x):
        h = x
        x = self.pre_norm(x)
        x = x.transpose(-1, -2)
        x = self.token_mlp_block(x)
        x = x.transpose(-1, -2)
        x = x + h

        h = x
        x = self.post_norm(x)
        x = self.channel_mlp_block(x)
        x = x + h
        return x
    
class PrunBlock(nn.Module):
    def __init__(self, config):
        super(MixerBlock, self).__init__()
        self.token_mlp_block = MlpBlock(config.n_patches, config.tokens_mlp_dim)
        self.pre_norm = nn.LayerNorm(config.hidden_dim, eps=1e-6)
        self.post_norm = nn.LayerNorm(config.hidden_dim, eps=1e-6)

    def forward(self, x):
        h = x
        x = self.pre_norm(x)
        x = x.transpose(-1, -2)
        x = self.token_mlp_block(x)
        x = x.transpose(-1, -2)
        x = x + h

        h = x
        x = self.post_norm(x)
        x = x + h
        return x
class MixerBlock(nn.Module):
    def __init__(self, config):
        super(MixerBlock, self).__init__()
        self.token_mlp_block = MlpBlock(config.n_patches, config.tokens_mlp_dim)
        self.channel_mlp_block = MlpBlock(config.hidden_dim, config.channels_mlp_dim)
        self.pre_norm = nn.LayerNorm(config.hidden_dim, eps=1e-6)
        self.post_norm = nn.LayerNorm(config.hidden_dim, eps=1e-6)

    def forward(self, x):
        h = x
        x = self.pre_norm(x)
        x = x.transpose(-1, -2)
        x = self.token_mlp_block(x)
        x = x.transpose(-1, -2)
        x = x + h

        h = x
        x = self.post_norm(x)
        x = self.channel_mlp_block(x)
        x = x + h
        return x

class TTMixer(nn.Module):
    def __init__(self, config, img_size=224, num_classes=1000, patch_size=16, zero_head=False, target_list=None):
        super(TTMixer, self).__init__()
        self.zero_head = zero_head
        self.num_classes = num_classes
        patch_size = _pair(patch_size)
        n_patches = (img_size // patch_size[0]) * (img_size // patch_size[1])
        config.n_patches = n_patches

        self.stem = nn.Conv2d(in_channels=3,
                              out_channels=config.hidden_dim,
                              kernel_size=patch_size,
                              stride=patch_size)
        self.head = nn.Linear(config.hidden_dim, num_classes, bias=True)
        self.pre_head_ln = nn.LayerNorm(config.hidden_dim, eps=1e-6)


        self.layer = nn.ModuleList()
        for i in range(config.num_blocks):
            if (target_list is not None) and (i == target_list):
                layer = TTBlock(config)
            else:
                layer = MixerBlock(config)
                
            self.layer.append(copy.deepcopy(layer))

    def forward(self, x):
        x = self.stem(x)
        x = x.flatten(2)
        x = x.transpose(-1, -2)

        for block in self.layer:
            x = block(x)
        x = self.pre_head_ln(x)
        x = torch.mean(x, dim=1)
        logits = self.head(x)

        return logits

class PrunMixer(nn.Module):
    def __init__(self, config, img_size=224, num_classes=1000, patch_size=16, zero_head=False, target_list=None):
        super(TTMixer, self).__init__()
        self.zero_head = zero_head
        self.num_classes = num_classes
        patch_size = _pair(patch_size)
        n_patches = (img_size // patch_size[0]) * (img_size // patch_size[1])
        config.n_patches = n_patches

        self.stem = nn.Conv2d(in_channels=3,
                              out_channels=config.hidden_dim,
                              kernel_size=patch_size,
                              stride=patch_size)
        self.head = nn.Linear(config.hidden_dim, num_classes, bias=True)
        self.pre_head_ln = nn.LayerNorm(config.hidden_dim, eps=1e-6)


        self.layer = nn.ModuleList()
        for i in range(config.num_blocks):
            if (target_list is not None) and (i == target_list):
                layer = PrunBlock(config)
            else:
                layer = MixerBlock(config)
                
            self.layer.append(copy.deepcopy(layer))

    def forward(self, x):
        x = self.stem(x)
        x = x.flatten(2)
        x = x.transpose(-1, -2)

        for block in self.layer:
            x = block(x)
        x = self.pre_head_ln(x)
        x = torch.mean(x, dim=1)
        logits = self.head(x)

        return logits

CONFIGS = {
    'Mixer-B_16': configs.get_mixer_b16_config(),
    'Mixer-L_16': configs.get_mixer_l16_config(),
    'Mixer-B_16-21k': configs.get_mixer_b16_config(),
    'Mixer-L_16-21k': configs.get_mixer_l16_config()
}
