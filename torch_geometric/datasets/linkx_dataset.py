import os.path as osp
from typing import Callable, List, Optional

import numpy as np
import torch
import torch.nn.functional as F

from torch_geometric.data import Data, InMemoryDataset, download_url


class LINKXDataset(InMemoryDataset):
    r"""A variety of non-homophilous graph datasets from the `"Large Scale
    Learning on Non-Homophilous Graphs: New Benchmarks and Strong Simple
    Methods" <https://arxiv.org/abs/2110.14446>`_ paper.

    .. note::
        Some of the datasets provided in :class:`LINKXDataset` are from other
        sources, but have been updated with new features and/or labels.

    Args:
        root (string): Root directory where the dataset should be saved.
        name (string): The name of the dataset (:obj:`"penn94"`,
            :obj:`"reed98"`, :obj:`"amherst41"`, :obj:`"cornell5"`,
            :obj:`"johnshopkins55"`, :obj:`"genius"`).
        transform (callable, optional): A function/transform that takes in an
            :obj:`torch_geometric.data.Data` object and returns a transformed
            version. The data object will be transformed before every access.
            (default: :obj:`None`)
        pre_transform (callable, optional): A function/transform that takes in
            an :obj:`torch_geometric.data.Data` object and returns a
            transformed version. The data object will be transformed before
            being saved to disk. (default: :obj:`None`)
    """

    url = 'https://github.com/CUAI/Non-Homophily-Large-Scale/raw/master/data'

    facebook_datasets = [
        'penn94', 'reed98', 'amherst41', 'cornell5', 'johnshopkins55'
    ]

    datasets = {
        'penn94': f'{url}/facebook100/Penn94.mat',
        'reed98': f'{url}/facebook100/Reed98.mat',
        'amherst41': f'{url}/facebook100/Amherst41.mat',
        'cornell5': f'{url}/facebook100/Cornell5.mat',
        'johnshopkins55': f'{url}/facebook100/Johns%20Hopkins55.mat',
        'genius': f'{url}/genius.mat'
    }

    splits = {
        'penn94': f'{url}/splits/fb100-Penn94-splits.npy',
    }

    def __init__(self, root: str, name: str,
                 transform: Optional[Callable] = None,
                 pre_transform: Optional[Callable] = None):
        self.name = name.lower()
        assert self.name in self.datasets.keys()
        super().__init__(root, transform, pre_transform)
        self.data, self.slices = torch.load(self.processed_paths[0])

    @property
    def raw_dir(self) -> str:
        return osp.join(self.root, self.name, 'raw')

    @property
    def processed_dir(self) -> str:
        return osp.join(self.root, self.name, 'processed')

    @property
    def raw_file_names(self) -> List[str]:
        names = [self.datasets[self.name].split('/')[-1]]
        if self.name in self.splits:
            names += [self.splits[self.name].split('/')[-1]]
        return names

    @property
    def processed_file_names(self) -> str:
        return 'data.pt'

    def download(self):
        download_url(self.datasets[self.name], self.raw_dir)
        if self.name in self.splits:
            download_url(self.splits[self.name], self.raw_dir)

    def _process_facebook(self):
        from scipy.io import loadmat

        mat = loadmat(self.raw_paths[0])

        A = mat['A'].tocsr().tocoo()
        row = torch.from_numpy(A.row).to(torch.long)
        col = torch.from_numpy(A.col).to(torch.long)
        edge_index = torch.stack([row, col], dim=0)

        metadata = torch.from_numpy(mat['local_info'].astype('int64'))

        xs = []
        y = metadata[:, 1] - 1  # gender label, -1 means unlabeled
        x = torch.cat([metadata[:, :1], metadata[:, 2:]], dim=-1)
        for i in range(x.size(1)):
            _, out = x[:, i].unique(return_inverse=True)
            xs.append(F.one_hot(out).to(torch.float))
        x = torch.cat(xs, dim=-1)

        data = Data(x=x, edge_index=edge_index, y=y)

        if self.name in self.splits:
            splits = np.load(self.raw_paths[1], allow_pickle=True)
            sizes = (data.num_nodes, len(splits))
            data.train_mask = torch.zeros(sizes, dtype=torch.bool)
            data.val_mask = torch.zeros(sizes, dtype=torch.bool)
            data.test_mask = torch.zeros(sizes, dtype=torch.bool)

            for i, split in enumerate(splits):
                data.train_mask[:, i][torch.tensor(split['train'])] = True
                data.val_mask[:, i][torch.tensor(split['valid'])] = True
                data.test_mask[:, i][torch.tensor(split['test'])] = True

        return data

    def _process_genius(self):
        from scipy.io import loadmat

        mat = loadmat(self.raw_paths[0])
        edge_index = torch.from_numpy(mat['edge_index']).to(torch.long)
        x = torch.from_numpy(mat['node_feat']).to(torch.float)
        y = torch.from_numpy(mat['label']).squeeze().to(torch.long)

        return Data(x=x, edge_index=edge_index, y=y)

    def process(self):
        if self.name in self.facebook_datasets:
            data = self._process_facebook()
        elif self.name == 'genius':
            data = self._process_genius()
        else:
            raise NotImplementedError

        if self.pre_transform is not None:
            data = self.pre_transform(data)

        torch.save(self.collate([data]), self.processed_paths[0])

    def __repr__(self) -> str:
        return f'{self.name.capitalize()}({len(self)})'
