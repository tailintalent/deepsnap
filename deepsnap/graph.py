import re
import random
import copy
import math
import pdb
import numpy as np
import torch
import networkx as nx
from torch_geometric.utils import to_undirected
from typing import (
    Dict,
    List,
    Union,
)
import warnings


class Graph(object):
    r"""
    A plain python object modeling a single graph with various
    (optional) attributes:

    Args:
        G (:class:`networkx.classes.graph`): The NetworkX graph object which contains features
             and labels for the tasks.
        **kwargs: keyworded argument list with keys such as :obj:`"node_feature"`, :obj:`"node_label"`
            and corresponding attributes.
    """

    def __init__(self, G=None, **kwargs):
        self.G = G
        keys = [
            "node_feature",
            "node_label",
            "edge_feature",
            "edge_label",
            "graph_feature",
            "graph_label",
            "edge_index",
            "edge_label_index",
            "node_label_index",
            "custom",
            "task"
        ]
        for key in keys:
            self[key] = None

        for key, item in kwargs.items():
            self[key] = item

        if G is None and kwargs:
            if "directed" not in kwargs:
                self.directed = True
            if "edge_index" not in kwargs:
                raise ValueError(
                    "A tensor of edge_index is required by using "
                    "the tensor backend."
                )
            # check for undirected edge_index format
            if not self.directed:
                edge_index_length = self.edge_index.shape[1]
                edge_index_first_half, _ = (
                    torch.sort(self.edge_index[:, :int(edge_index_length / 2)])
                )
                edge_index_second_half, _ = (
                    torch.sort(self.edge_index[:, int(edge_index_length / 2):])
                )
                if not torch.equal(
                    edge_index_first_half,
                    torch.flip(edge_index_second_half, [0])
                ):
                    raise ValueError(
                        "In tensor backend mode with undirected graph, "
                        "the user provided edge_index should contain "
                        "undirected edges for both directions."
                        "the first half of edge_index should contain "
                        "unique edges in one direction and the second "
                        "half of edge_index should contain the same set "
                        "of unique edges of another direction."
                    )

        if G is not None or kwargs:
            if (
                ("edge_label_index" not in kwargs)
                and ("node_label_index" not in kwargs)
            ):
                self._update_tensors(init=True)
            else:
                self._update_tensors(init=False)
        self._num_positive_examples = None

    @classmethod
    def _from_dict(cls, dictionary: Dict[str, torch.tensor]):
        r"""
        Creates a data object from a python dictionary.

        Args:
            dictionary (dict): Python dictionary with key (string) - value (torch.tensor) pair.

        Returns:
            :class:`deepsnap.graph.Graph`: return a new Graph object with the data from the dictionary.
        """
        if "G" in dictionary:
            # If there is an G, initialize class in the graph backend
            graph = cls(G=dictionary["G"])
        else:
            graph = cls(**dictionary)
        for key, item in dictionary.items():
            graph[key] = item

        return graph

    def __getitem__(self, key: str):
        r"""
        Gets the data of the attribute :obj:`key`.
        """
        return getattr(self, key, None)

    def __setitem__(self, key: str, value):
        """Sets the attribute :obj:`key` to :obj:`value`."""
        setattr(self, key, value)

    @property
    def keys(self):
        r"""
        Returns all names of the graph attributes.

        Returns:
            list: List of :class:`deepsnap.graph.Graph` attributes.
        """
        # filter attributes that are not observed by users
        # (1) those with value "None"; (2) those start with '_'
        keys = [
            key
            for key in self.__dict__.keys()
            if self[key] is not None and key[0] != "_"
        ]
        return keys

    def __len__(self) -> int:
        r"""
        Returns the number of all present attributes.

        Returns:
            int: The number of all present attributes.
        """
        return len(self.keys)

    def __contains__(self, key: str) -> bool:
        r"""
        Returns :obj:`True`, if the attribute :obj:`key` is present in the
        data.
        """
        return key in self.keys

    def __iter__(self):
        r"""
        Iterates over all present attributes in the data, yielding their
        attribute names and content.
        """
        for key in sorted(self.keys):
            yield key, self[key]

    def __call__(self, *keys):
        r"""
        Iterates over all attributes :obj:`*keys` in the data, yielding
        their attribute names and content.
        If :obj:`*keys` is not given this method will iterative over all
        present attributes.
        """
        for key in sorted(self.keys) if not keys else keys:
            if key in self:
                yield key, self[key]

    def __cat_dim__(self, key: str, value) -> int:
        r"""
        Returns the dimension for which :obj:`value` of attribute
        :obj:`key` will get concatenated when creating batches.

        .. note::

            This method is for internal use only, and should only be overridden
            if the batch concatenation process is corrupted for a specific data
            attribute.
        """
        # `*index*` and `*face*` should be concatenated in the last dimension,
        # everything else in the first dimension.
        return -1 if "index" in key else 0

    def __inc__(self, key: str, value) -> int:
        r""""
        Returns the incremental count to cumulatively increase the value
        of the next attribute of :obj:`key` when creating batches.

        .. note::

            This method is for internal use only, and should only be overridden
            if the batch concatenation process is corrupted for a specific data
            attribute.
        """
        # Only `*index*` and `*face*` should be cumulatively summed up when
        # creating batches.
        return self.num_nodes if "index" in key else 0

    @property
    def num_nodes(self) -> int:
        r"""
        Return number of nodes in the graph.

        Returns:
            int: Number of nodes in the graph.
        """
        if self.G is not None:
            return self.G.number_of_nodes()
        return self[self._node_related_key].shape[0]

    @property
    def num_edges(self) -> int:
        r"""
        Returns number of edges in the graph.

        Returns:
            int: Number of edges.
        """
        if self.G is not None:
            return self.G.number_of_edges()
        if self.is_undirected():
            return int(self.edge_index.shape[1] / 2)
        return self.edge_index.shape[1]

    @property
    def num_node_features(self) -> int:
        r"""
        Returns node feature dimension in the graph.

        Returns:
            int: Node feature dimension and `0` if there is no `node_feature`.
        """
        return self.get_num_dims("node_feature", as_label=False)

    @property
    def num_node_labels(self) -> int:
        r"""
        Returns number of the node labels in the graph.

        Returns:
            int: Number of node labels and `0` if there is no `node_label`.
        """
        return self.get_num_dims("node_label", as_label=True)

    @property
    def num_edge_features(self) -> int:
        r"""
        Returns edge feature dimension in the graph.

        Returns:
            int: Node feature dimension and `0` if there is no `edge_feature`.
        """
        return self.get_num_dims("edge_feature", as_label=False)

    @property
    def num_edge_labels(self) -> int:
        r"""
        Returns number of the edge labels in the graph.

        Returns:
            int: Number of edge labels and `0` if there is no `edge_label`.
        """
        return self.get_num_dims("edge_label", as_label=True)

    @property
    def num_graph_features(self) -> int:
        r"""
        Returns graph feature dimension in the graph.

        Returns:
            int: Graph feature dimension and `0` if there is no
            `graph_feature`.
        """
        return self.get_num_dims("graph_feature", as_label=False)

    @property
    def num_graph_labels(self) -> int:
        r"""
        Returns number of the graph labels in the graph.

        Returns:
            int: Number of graph labels and `0` if there is no `graph_label`.
        """
        return self.get_num_dims("graph_label", as_label=True)

    def get_num_dims(self, key, as_label=False) -> int:
        r"""
        Returns the number of dimensions for one graph/node/edge property.

        Args:
            as_label: if as_label, treat the tensor as labels (
        """
        if as_label:
            # treat as label
            if self[key] is not None:
                if self[key].dtype == torch.long:
                    # classification label
                    return torch.max(self[key]).item() + 1
                else:
                    # regression label
                    if (
                        len(self[key].shape) == 1
                        and not Graph._is_graph_attribute(key)
                    ):
                        # for node/edge tasks: 1 scalar per node/edge
                        return 1
                    else:
                        return self[key].shape[-1]
            else:
                return 0
        else:
            # treat as feature
            if self[key] is not None:
                return self[key].shape[1]
            else:
                return 0

    def is_directed(self) -> bool:
        r"""
        Whether the graph is directed.

        Returns:
            bool: :obj:`True` if the graph is directed.
        """
        if self.G is not None:
            return self.G.is_directed()
        return self.directed

    def is_undirected(self) -> bool:
        r"""
        Whether the graph is undirected.

        Returns:
            bool: :obj:`True` if the graph is undirected.
        """
        return not self.is_directed()

    def apply_tensor(self, func, *keys):
        r"""
        Applies the function :obj:`func` to all tensor attributes
        :obj:`*keys`. If :obj:`*keys` is not given, :obj:`func` is applied to
        all present attributes.

        Args:
            func (function): a function can be applied to a PyTorch tensor.
            *keys (string, optional): names of the tensor attributes that will be applied.

        Returns:
            :class:`deepsnap.graph.Graph`: Return the self :class:`deepsnap.graph.Graph`.
        """
        for key, item in self(*keys):
            if torch.is_tensor(item):
                self[key] = func(item)
            elif isinstance(self[key], dict):
                for obj_key, obj_item in self[key].items():
                    if torch.is_tensor(obj_item):
                        self[key][obj_key] = func(obj_item)
        return self

    def contiguous(self, *keys):
        r"""
        Ensures a contiguous memory layout for the attributes specified by
        :obj:`*keys`. If :obj:`*keys` is not given, all present attributes
        are ensured tohave a contiguous memory layout.

        Args:
            *keys (string, optional): tensor attributes which will be in contiguous memory layout.

        Returns:
            :class:`deepsnap.graph.Graph`: :class:`deepsnap.graph.Graph` object with specified tensor attributes in contiguous memory layout.
        """
        return self.apply_tensor(lambda x: x.contiguous(), *keys)

    def to(self, device, *keys):
        r"""
        Performs tensor dtype and/or device conversion to all attributes
        :obj:`*keys`.
        If :obj:`*keys` is not given, the conversion is applied to all present
        attributes.

        Args:
            device: Specified device name.
            *keys (string, optional): Tensor attributes which will transfer to the specified device.
        """
        return self.apply_tensor(lambda x: x.to(device), *keys)

    def clone(self):
        r"""
        Deepcopy the graph object.

        Returns:
            :class:`deepsnap.graph.Graph`: A cloned :class:`deepsnap.graph.Graph` object with deepcopying all features.
        """
        return self.__class__._from_dict(
            {
                k: v.clone() if torch.is_tensor(v) else copy.deepcopy(v)
                for k, v in self.__dict__.items()
            }
        )

    def _size_repr(self, value) -> List[int]:
        r"""
        Returns:
            list: A list of size of each element in value
        """
        if torch.is_tensor(value):
            return list(value.size())
        elif isinstance(value, int) or isinstance(value, float):
            return [1]
        elif isinstance(value, list) or isinstance(value, tuple):
            return [len(value)]
        else:
            return []

    def __repr__(self):
        info = [f"{key}={self._size_repr(item)}" for key, item in self]
        return f"{self.__class__.__name__}({', '.join(info)})"

    @staticmethod
    def _is_edge_attribute(key: str) -> bool:
        r"""
        Check whether an attribute is a edge attribute.
        """
        # could be feature, label, etc.
        return "edge" in key and "index" not in key

    @staticmethod
    def _is_node_attribute(key: str) -> bool:
        r"""
        Check whether an attribute is a node attribute.
        """
        # could be feature, label, etc.
        return "node" in key and "index" not in key

    @staticmethod
    def _is_graph_attribute(key: str) -> bool:
        r"""
        Check whether an attribute is a graph attribute.
        """
        return "graph" in key and "index" not in key

    def _is_valid(self):
        r"""
        Check validity.
        """
        for key in self.keys:
            if self._is_node_attribute(key):
                assert self.num_nodes == self[key].size(
                    0
                ), f"key {key} is not valid, num nodes must equal num nodes w/ features"

    def _update_tensors(self, init: bool = False):
        r"""
        Update attributes and edge indices with values from the .G graph object.
        """
        if self.G is not None:
            self._update_attributes()
        self._node_related_key = None
        for key in self.keys:
            if self._is_node_attribute(key):
                self._node_related_key = key
                break
        if self._node_related_key is None:
            warnings.warn("Node related key is required.")

        self._update_index(init)

    def _update_attributes(self):
        r"""
        Update attributes
        """
        # node
        if self.G.number_of_nodes() == 0:
            raise ValueError(
                "in _update_attributes, number of nodes in Graph "
                "G must be larger than 0"
            )
        if self.G.number_of_edges() == 0:
            raise ValueError(
                "in _update_attributes, number of edges in Graph "
                "G must be larger than 0"
            )

        keys = next(iter(self.G.nodes(data=True)))[-1].keys()
        for key in keys:
            self[key] = self._get_node_attributes(key)
        # edge
        keys = next(iter(self.G.edges(data=True)))[-1].keys()
        for key in keys:
            self[key] = self._get_edge_attributes(key)
        # graph
        keys = self.G.graph.keys()
        for key in keys:
            self[key] = self._get_graph_attributes(key)

    def _get_node_attributes(self, name: str):
        r"""
        Returns the node attributes in the graph. Multiple attributes will be stacked.

        Args:
            name(string): the name of the attributes to return.

        Returns:
            :class:`torch.tensor`: Node attributes.
        """
        # new: concat
        attributes = []
        for _, d in self.G.nodes.items():
            if name in d:
                attributes.append(d[name])
        if len(attributes) == 0:
            return None
        if torch.is_tensor(attributes[0]):
            attributes = torch.stack(attributes, dim=0)
        elif isinstance(attributes[0], float):
            attributes = torch.tensor(attributes, dtype=torch.float)
        elif isinstance(attributes[0], int):
            attributes = torch.tensor(attributes, dtype=torch.long)

        return attributes

    def _get_edge_attributes(self, key: str):
        r"""
        Returns the edge attributes in the graph. Multiple attributes will be stacked.

        Args:
            key(string): the name of the attributes to return.

        Returns:
            :class:`torch.tensor`: Edge attributes.
        """

        # new: concat
        attributes = []
        for x in self.G.edges(data=True):
            if key in x[-1]:
                attributes.append(x[-1][key])
        if len(attributes) == 0:
            return None
        if torch.is_tensor(attributes[0]):
            attributes = torch.stack(attributes, dim=0)
        elif isinstance(attributes[0], float):
            attributes = torch.tensor(attributes, dtype=torch.float)
        elif isinstance(attributes[0], int):
            attributes = torch.tensor(attributes, dtype=torch.long)
        else:
            raise TypeError(f"Unknown type {key} in edge attributes.")

        if self.is_undirected():
            attributes = torch.cat([attributes, attributes], dim=0)

        return attributes

    def _get_graph_attributes(self, key: str):
        r"""
        Returns the graph attributes.

        Args:
            key(string): the name of the attributes to return.

        Returns:
            any: graph attributes with the specified name.
        """
        return self.G.graph.get(key)

    def _update_edges(self, edges, mapping, add_edge_info=True):
        r"""
        TODO: add comments
        """
        for i in range(len(edges)):
            node_0 = mapping[
                edges[i][0]
            ]
            node_1 = mapping[
                edges[i][1]
            ]

            if isinstance(edges[i][-1], dict):
                edge_info = edges[i][-1]
                if len(edges[i][:-1]) == 2:
                    edge = (node_0, node_1, edge_info)
                elif len(edges[i][:-1]) == 3:
                    graph_index = edges[i][2]
                    edge = (node_0, node_1, graph_index, edge_info)
                else:
                    raise ValueError("Each edge has more than 3 indices.")
            else:
                if len(edges[i]) == 2:
                    if add_edge_info:
                        if self.G is not None:
                            edge = (
                                node_0, node_1, self.G.edges[node_0, node_1]
                            )
                        else:
                            feature_dict = {}
                            for key in self.keys:
                                if (
                                    Graph._is_edge_attribute(key)
                                    and key != "edge_index"
                                ):
                                    if torch.is_tensor(self[key]):
                                        # TODO: check shape?
                                        feature_dict[key] = self[key][i]
                            edge = (node_0, node_1, feature_dict)
                    else:
                        edge = (node_0, node_1)
                elif len(edges[i]) == 3:
                    graph_index = edges[i][2]
                    if add_edge_info:
                        if self.G is not None:
                            edge = (
                                node_0, node_1, graph_index,
                                self.G.edges[node_0, node_1, graph_index]
                            )
                        else:
                            feature_dict = {}
                            for key in self.keys:
                                if (
                                    Graph._is_edge_attribute(key)
                                    and key != "edge_index"
                                ):
                                    if torch.is_tensor(self[key]):
                                        # TODO: check shape?
                                        feature_dict[key] = self[key][i]
                            edge = (node_0, node_1, feature_dict)
                    else:
                        edge = (node_0, node_1, graph_index)
                else:
                    raise ValueError("Each edge has more than 3 indices.")

            edges[i] = edge
        return edges

    def _custom_update(self):
        custom_keys = [
            "general_splits", "disjoint_split", "negative_edges", "task"
        ]
        if self.custom is not None:
            for custom_key in custom_keys:
                if custom_key in self.custom:
                    self[custom_key] = self.custom[custom_key]
                else:
                    self[custom_key] = None

    def _update_index(self, init=False):
        # TODO: add validity check for general_splits
        # TODO: add validity check for disjoint_split
        # TODO: add validity check for negative_edge
        # relabel graphs
        if self.G is not None:
            keys = list(self.G.nodes)
            vals = list(range(self.num_nodes))
            mapping = dict(zip(keys, vals))
            if keys != vals:
                self.G = nx.relabel_nodes(self.G, mapping, copy=True)
            # get edges
            self.edge_index = self._edge_to_index(list(self.G.edges))
        else:
            mapping = {x: x for x in range(self.num_nodes)}
        if init:
            # init is only true when creating the variables
            # edge_label_index and node_label_index
            self.edge_label_index = copy.deepcopy(self.edge_index)
            self.node_label_index = (
                torch.arange(self.num_nodes, dtype=torch.long)
            )

            self._custom_update()
            if self.task is not None:
                if self.general_splits is not None:
                    if self.task == "node":
                        for i in range(len(self.general_splits)):
                            nodes = self.general_splits[i]
                            nodes = [
                                mapping[node]
                                for node in nodes
                            ]
                            self.general_splits[i] = torch.tensor(nodes)
                    elif self.task == "edge" or self.task == "link_pred":
                        for i in range(len(self.general_splits)):
                            self.general_splits[i] = self._update_edges(
                                self.general_splits[i],
                                mapping
                            )

                if self.disjoint_split is not None:
                    if self.task == "link_pred":
                        self.disjoint_split = self._update_edges(
                            self.disjoint_split,
                            mapping
                        )
                    else:
                        raise ValueError(
                            "When self.disjoint_splits is not "
                            "None, self.task must be `link_pred`"
                        )

                if self.negative_edges is not None:
                    if self.task == "link_pred":
                        for i in range(len(self.negative_edges)):
                            self.negative_edges[i] = self._update_edges(
                                self.negative_edges[i],
                                mapping,
                                add_edge_info=False
                            )
                    else:
                        raise ValueError(
                            "When self.negative_edges is not "
                            "None, self.task must be `link_pred`"
                        )

    def _edge_to_index(self, edges):
        r"""
        List of G.edges to torch tensor edge_index

        Only the selected edges' edge indices are extracted.
        """
        edges = [(edge[0], edge[1]) for edge in edges]

        edge_index = torch.tensor(edges)
        if self.is_undirected():
            edge_index = torch.cat(
                [edge_index, torch.flip(edge_index, [1])],
                dim=0
            )
        return edge_index.permute(1, 0)

    def _get_edge_attributes_by_key(self, edges, key: str):
        r"""
        List of G.edges to torch tensor for key, with dimension [num_edges x key_dim].

        Only the selected edges' attributes are extracted.
        """
        if len(edges) == 0:
            raise ValueError(
                "in _get_edge_attributes_by_key, "
                "len(edges) must be larger than 0."
            )
        if not isinstance(edges[0][-1], dict) or key not in edges[0][-1]:
            return None

        attributes = [edge[-1][key] for edge in edges]
        if torch.is_tensor(attributes[0]):
            attributes = torch.stack(attributes, dim=0)
        elif isinstance(attributes[0], float):
            attributes = torch.tensor(attributes, dtype=torch.float)
        elif isinstance(attributes[0], int):
            attributes = torch.tensor(attributes, dtype=torch.long)
        else:
            raise ValueError("Unknown type of key {} in edge attributes.")

        if self.is_undirected():
            attributes = torch.cat([attributes, attributes], dim=0)

        return attributes

    def _get_edge_attributes_by_key_tensor(self, edge_index, key: str):
        r"""
        Extract the edge attributes indicated by edge_index in tensor backend.
        """
        if not torch.is_tensor(edge_index):
            raise TypeError(
                "edge_index is not in the correct format."
            )
        if key == "edge_index":
            raise ValueError(
                "edge_index cannot be selected."
            )
        if key not in self.keys or not torch.is_tensor(self[key]):
            return None
        attributes = torch.index_select(self[key], 0, edge_index)
        if self.is_undirected():
            attributes = torch.cat([attributes, attributes], dim=0)
        return attributes

    def _update_graphs(self, verbose=False):
        r"""
        Update the .G graph object with new attributes.
        The edges remain unchanged (edge_index should not be directly modified).

        The counter-part of update_tensors.
        """
        for key in self.keys:
            if Graph._is_node_attribute(key):
                Graph.add_node_attr(self.G, key, self[key])
            elif Graph._is_edge_attribute(key):
                # the order of edge attributes is consistent with edge index
                Graph.add_edge_attr(self.G, key, self[key])
            elif Graph._is_graph_attribute(key):
                Graph.add_graph_attr(self.G, key, self[key])
            else:
                if verbose:
                    print(f"Index fields: {key} ignored.")

    def apply_transform(
        self,
        transform,
        update_tensor: bool = True,
        update_graph: bool = False,
        deep_copy: bool = False,
        **kwargs,
    ):
        r"""
        Applies transform function to the current graph object.

        Note that when the backend graph object (e.g. networkx object) is changed in the
        transform function, the argument update_tensor is recommended, to update the tensor
        representation to be in sync with the transformed graph.
        Similarly, update_graph is recommended when the transform function makes change to
        the tensor objects.

        However, the transform function should not make changes to both the backend graph
        object and the tensors simultaneously. Otherwise there might exist inconsistency
        between the transformed graph and tensors.
        Also note that update_tensor and update_graph cannot be true at the same time.

        It is also possible to set both update_tensor and update_graph to be False.
        This usually happens when one needs to transform the tensor representation, but do not
        require that the internal graph object to be in sync, for better efficiency.
        In this case, the user should note that the internal .G object is stale, and that
        applying a transform in the future with update_tensor=True will overwrite the
        current transform (with parameters update_tensor=False; update_graph=False).

        Args:
            transform (fuction): in the format of :obj:`transform(deepsnap.graph.Graph, **kwargs)`.
                The function needs to either return deepsnap.graph.Graph (the transformed graph
                object), or the transformed internal .G object (networkx).
                If returning .G object, all corresponding tensors will be updated.
            update_tensor (boolean): if nx graph has changed,
                use nx graph to update tensor attributes.
            update_graph: (boolean): if tensor attributes has changed,
                use attributes to update nx graph.
            deep_copy (boolean): True if a new copy of graph_object is needed.
                In this case, the transform function needs to either return a graph object,
                Important: when returning Graph object in transform function, user should decide
                whether the tensor values of the graph is to be copied (deep copy).
            **kwargs (any): additional args for the transform function.

        Returns:
            a transformed Graph object.

        Note:
            This function different from the function :obj:`apply_tensor`.
        """
        if update_tensor and update_graph:
            raise ValueError("Tensor and graph should not be specified together.")
        graph_obj = copy.deepcopy(self) if deep_copy else self
        return_graph = transform(graph_obj, **kwargs)

        if isinstance(return_graph, self.__class__):
            return_graph = return_graph
        elif return_graph is None:
            # no return value; assumes in-place transform of the graph object
            return_graph = graph_obj
        else:
            raise TypeError(
                "Transform function returns a value of unknown type ({return_graph.__class__})"
            )
        if update_graph:
            if self.G is None:
                raise ValueError("There is no G in the class.")
            return_graph._update_graphs()
        if update_tensor:
            return_graph._update_tensors()
        return return_graph

    def apply_transform_multi(
        self,
        transform,
        update_tensors: bool = True,
        update_graphs: bool = False,
        deep_copy: bool = False,
        **kwargs,
    ):
        r"""
        Applies transform function to the current graph object.

        Unlike apply_transform, the transform argument in this method can return
        a tuple of graphs (Graph or internal NetworkX Graphs).

        Args:
            transform (fuction): in the format of :obj:`transform(deepsnap.graph.Graph, **kwargs)`.
                The function needs to either return a tuple of deepsnap.graph.Graph (the transformed graph
                object), or a tuple of internal .G object (NetworkX).
                If returning .G object, all corresponding tensors will be updated.

        Returns:
            a tuple of transformed Graph objects.
        """
        if update_tensors and update_graphs:
            raise ValueError("Tensor and graph should not be specified together.")
        graph_obj = copy.deepcopy(self) if deep_copy else self
        return_graphs = transform(graph_obj, **kwargs)

        if isinstance(return_graphs[0], self.__class__):
            return_graphs = return_graphs
        elif return_graphs is None or len(return_graphs) == 0:
            # no return value; assumes in-place transform of the graph object
            return_graphs = (graph_obj,)
        else:
            raise TypeError(
                "Transform function returns a value of unknown type ({return_graphs[0].__class__)})"
            )
        if update_graphs:
            for return_graph in return_graphs:
                if self.G is None:
                    raise ValueError("There is no G in the class.")
                return_graph._update_graphs()
        if update_tensors:
            for return_graph in return_graphs:
                return_graph._update_tensors()
        return return_graphs

    def split(self, task: str = "node", split_ratio: List[float] = None):
        r"""
        Split current graph object to list of graph objects.

        Args:
            task (string): one of `node`, `edge` or `link_pred`.
            split_ratio (array_like): array_like ratios `[train_ratio, validation_ratio, test_ratio]`.

        Returns:
            list: A Python list of :class:`deepsnap.graph.Graph` objects with specified task.
        """
        if split_ratio is None:
            split_ratio = [0.8, 0.1, 0.1]
        if not isinstance(split_ratio, list):
            raise TypeError("split ratio must be a list.")
        if len(split_ratio) > 3:
            raise ValueError("split ratio must contain leq three values")
        if not math.isclose(sum(split_ratio), 1.0):
            raise ValueError("split ratio must sum up to 1.")
        if not all(
            isinstance(split_ratio_i, float) for split_ratio_i in split_ratio
        ):
            raise TypeError("split ratio must contain all floats")
        if not all(split_ratio_i > 0 for split_ratio_i in split_ratio):
            raise ValueError("split ratio must contain all positivevalues.")

        if task == "node":
            return self._split_node(split_ratio)
        elif task == "edge":
            return self._split_edge(split_ratio)
        elif task == "link_pred":
            return self.split_link_pred(split_ratio)
        elif task == "graph":
            raise ValueError("Graph task does not split individual graphs.")
        else:
            raise ValueError("Unknown task.")

    def _split_node(self, split_ratio: float):
        r"""
        Split the graph into len(split_ratio) graphs for node prediction.
        Internally this splits node indices, and the model will only compute
        loss for the embedding of
        nodes in each split graph.
        In node classification, the whole graph is observed in train/val/test
        Only split over node_label_index
        """
        if self.num_nodes < len(split_ratio):
            raise ValueError(
                "in _split_node num of nodes are smaller than"
                "number of splitted parts"
            )

        split_graphs = []
        shuffled_node_indices = torch.randperm(self.num_nodes)
        split_offset = 0

        # perform `secure split` s.t. guarantees all splitted subgraph
        # contains at least one node.
        for i, split_ratio_i in enumerate(split_ratio):
            if i != len(split_ratio) - 1:
                num_split_i = 1 + int(
                    split_ratio_i * (self.num_nodes - len(split_ratio))
                )
                nodes_split_i = shuffled_node_indices[
                    split_offset:split_offset + num_split_i
                ]
                split_offset += num_split_i
            else:
                nodes_split_i = shuffled_node_indices[split_offset:]
            # shallow copy all attributes
            graph_new = copy.copy(self)
            graph_new.node_label_index = nodes_split_i
            graph_new.node_label = self.node_label[nodes_split_i]
            split_graphs.append(graph_new)
        return split_graphs

    def _split_edge(self, split_ratio: float):
        r"""
        Split the graph into len(split_ratio) graphs for node prediction.
        Internally this splits node indices, and the model will only compute
        loss for the embedding of nodes in each split graph.
        In edge classification, the whole graph is observed in train/val/test.
        Only split over edge_label_index.
        """
        if self.num_edges < len(split_ratio):
            raise ValueError(
                "in _split_node num of edges are smaller than"
                "number of splitted parts"
            )

        split_graphs = []
        shuffled_edge_indices = torch.randperm(self.num_edges)
        split_offset = 0

        # perform `secure split` s.t. guarantees all splitted subgraph
        # contains at least one edge.
        for i, split_ratio_i in enumerate(split_ratio):
            if i != len(split_ratio) - 1:
                num_split_i = 1 + int(
                    split_ratio_i * (self.num_edges - len(split_ratio))
                )
                edges_split_i = shuffled_edge_indices[
                    split_offset:split_offset + num_split_i
                ]
                split_offset += num_split_i
            else:
                edges_split_i = shuffled_edge_indices[split_offset:]
            # shallow copy all attributes
            graph_new = copy.copy(self)
            graph_new.edge_label_index = self.edge_index[:, edges_split_i]
            graph_new.edge_label = self.edge_label[edges_split_i]
            split_graphs.append(graph_new)
        return split_graphs

    def _custom_split_link_pred_disjoint(self):
        objective_edges = self.disjoint_split
        objective_edges_no_info = [edge[:-1] for edge in objective_edges]
        message_edges_no_info = (
            list(set(self.G.edges) - set(objective_edges_no_info))
        )
        if len(message_edges_no_info[0]) == 3:
            message_edges = [
                (
                    edge[0], edge[1], edge[2],
                    self.G.edges[edge[0], edge[1], edge[2]]
                )
                for edge in message_edges_no_info
            ]
        elif len(message_edges_no_info[0]) == 2:
            message_edges = [
                (edge[0], edge[1], self.G.edges[edge[0], edge[1]])
                for edge in message_edges_no_info
            ]
        else:
            raise ValueError("Each edge has more than 3 indices.")
        graph_train = Graph(
            self._edge_subgraph_with_isonodes(
                self.G,
                message_edges,
            )
        )
        graph_train._create_label_link_pred(
            graph_train, objective_edges
        )
        return graph_train

    def _custom_split_link_pred(self):
        split_num = len(self.general_splits)
        split_graph = []

        edges_train = self.general_splits[0]
        edges_val = self.general_splits[1]

        graph_train = Graph(
            self._edge_subgraph_with_isonodes(
                self.G,
                edges_train,
            ),
            disjoint_split=(
                self.disjoint_split
            ),
            negative_edges=(
                self.negative_edges
            )
        )

        graph_val = copy.copy(graph_train)
        if split_num == 3:
            edges_test = self.general_splits[2]
            graph_test = Graph(
                self._edge_subgraph_with_isonodes(
                    self.G,
                    edges_train + edges_val
                ),
                negative_edges=(
                    self.negative_edges
                )
            )
        graph_train._create_label_link_pred(
            graph_train, edges_train
        )
        graph_val._create_label_link_pred(
            graph_val, edges_val
        )

        if split_num == 3:
            graph_test._create_label_link_pred(
                graph_test, edges_test
            )

        split_graph.append(graph_train)
        split_graph.append(graph_val)
        if split_num == 3:
            split_graph.append(graph_test)

        return split_graph

    def split_link_pred(self, split_ratio: Union[float, List[float]]):
        r"""
        Split the graph into len(split_ratio) graphs for link prediction.
        Internally this splits edge indices, and the model will only compute
        loss for the embedding of
        nodes in each split graph.
        This is only used for transductive link prediction task
        In this task, different part of graph is observed in train/val/test
        Note: this functon will be called twice,
        if during training, we further split the training graph so that
        message edges and objective edges are different
        """
        if isinstance(split_ratio, float):
            split_ratio = [split_ratio, 1 - split_ratio]
        if len(split_ratio) < 2 or len(split_ratio) > 3:
            raise ValueError("Unrecoginzed number of splits")
        if len(split_ratio) == 2:
            if self.num_edges < 2:
                raise ValueError(
                    "in split_link_pred num of edges are"
                    "smaller than number of splitted parts"
                )
        if len(split_ratio) == 3:
            if self.num_edges < 3:
                raise ValueError(
                    "in split_link_pred num of edges are"
                    "smaller than number of splitted parts"
                )

        if self.G is not None:
            edges = list(self.G.edges(data=True))
            random.shuffle(edges)
        else:
            edges = torch.randperm(self.num_edges)

        # Perform `secure split` s.t. guarantees all splitted subgraph
        # that contains at least one edge.
        if len(split_ratio) == 2:
            num_edges_train = 1 + int(split_ratio[0] * (self.num_edges - 2))

            edges_train = edges[:num_edges_train]
            edges_val = edges[num_edges_train:]
        elif len(split_ratio) == 3:
            num_edges_train = 1 + int(split_ratio[0] * (self.num_edges - 3))
            num_edges_val = 1 + int(split_ratio[1] * (self.num_edges - 3))

            edges_train = edges[:num_edges_train]
            edges_val = edges[num_edges_train:num_edges_train + num_edges_val]
            edges_test = edges[num_edges_train + num_edges_val:]

        if self.G is not None:
            graph_train = Graph(
                self._edge_subgraph_with_isonodes(self.G, edges_train)
            )
        else:
            graph_train = copy.copy(self)

            # update the edge_index
            edge_index = torch.index_select(
                self.edge_index, 1, edges_train
            )
            if self.is_undirected():
                edge_index = torch.cat(
                    [edge_index, torch.flip(edge_index, [0])], dim=1
                )

            # update edge features
            graph_train.edge_index = edge_index
            for key in graph_train.keys:
                if self._is_edge_attribute(key):
                    edge_feature = torch.index_select(
                        self[key], 0, edges_train
                    )
                    if self.is_undirected():
                        edge_feature = torch.cat(
                            [edge_feature, edge_feature], dim=0
                        )
                    graph_train[key] = edge_feature

        graph_val = copy.copy(graph_train)
        if len(split_ratio) == 3:
            if self.G is not None:
                graph_test = Graph(
                    self._edge_subgraph_with_isonodes(
                        self.G, edges_train + edges_val
                    )
                )
            else:
                graph_test = copy.copy(self)
                edge_index = torch.index_select(
                    self.edge_index, 1, torch.cat([edges_train, edges_val])
                )
                if self.is_undirected():
                    edge_index = torch.cat(
                        [edge_index, torch.flip(edge_index, [0])],
                        dim=1
                    )
                graph_test.edge_index = edge_index
                for key in graph_test.keys:
                    if self._is_edge_attribute(key):
                        edge_feature = torch.index_select(
                            self[key], 0, torch.cat([edges_train, edges_val])
                        )
                        if self.is_undirected():
                            edge_feature = torch.cat(
                                [edge_feature, edge_feature], dim=0
                            )
                        graph_test[key] = edge_feature

        self._create_label_link_pred(graph_train, edges_train)
        self._create_label_link_pred(graph_val, edges_val)
        if len(split_ratio) == 3:
            self._create_label_link_pred(graph_test, edges_test)
            return [graph_train, graph_val, graph_test]
        else:
            return [graph_train, graph_val]

    def _edge_subgraph_with_isonodes(self, G, edges):
        r"""
        Generate a new networkx graph with same nodes and their attributes.

        Preserves all nodes and a subset of edges. Nodes that are not connected
        by any of the edges will be isolated nodes instead of being removed.

        Note:
            edges should be list(G_i.edges(data=True))
        """
        G_new = G.__class__()
        G_new.add_nodes_from(G.nodes(data=True))
        G_new.add_edges_from(edges)
        return G_new

    def resample_disjoint(self, message_ratio):
        r""" Resample disjoint edge split of message passing and objective links.

        Note that if apply_transform (on the message passing graph)
        was used before this resampling, it needs to be
        re-applied, after resampling, to update some of the edges that were in objectives.
        """
        if not hasattr(self, "_objective_edges"):
            raise ValueError("No disjoint edge split was performed.")
        # Combine into 1 graph
        if self.G is not None:
            self.G.add_edges_from(self._objective_edges)
        else:
            edge_index = self.edge_index[:, 0:self.num_edges]

            # Concat the edge indices if objective is different with edge_index
            if not torch.equal(self._objective_edges, edge_index):
                edge_index = torch.cat(
                    (edge_index, self._objective_edges), dim=1
                )
                if self.is_undirected():
                    edge_index = torch.cat(
                        [edge_index, torch.flip(edge_index, [0])], dim=1
                    )
                self.edge_index = edge_index

        return self.split_link_pred(message_ratio)[1]

    def _create_label_link_pred(self, graph, edges):
        r"""
        Create edge label and the corresponding label_index (edges) for link prediction.

        Modifies the graph argument by setting the fields edge_label_index and edge_label.

        Notice when the graph is tensor backend, the edges are the indices of edges.
        """
        if self.G is not None:
            graph.edge_label_index = self._edge_to_index(edges)
            graph.edge_label = (
                self._get_edge_attributes_by_key(edges, "edge_label")
            )
            # Keep a copy of original edges (and their attributes)
            # for resampling the disjoint split (message passing and objective links)
            graph._objective_edges = edges
        else:
            edge_label_index = torch.index_select(
                self.edge_index, 1, edges
            )
            graph._objective_edges = edge_label_index
            if self.is_undirected():
                edge_label_index = torch.cat(
                    [edge_label_index, torch.flip(edge_label_index, [0])],
                    dim=1
                )
            graph.edge_label_index = edge_label_index
            graph.edge_label = (
                self._get_edge_attributes_by_key_tensor(edges, "edge_label")
            )

    def _custom_create_neg_sampling(
        self, negative_sampling_ratio: float, resample: bool = False
    ):
        if resample and self._num_positive_examples is not None:
            self.edge_label_index = self.edge_label_index[
                :, : self._num_positive_examples
            ]

        num_pos_edges = self.edge_label_index.shape[-1]
        num_neg_edges = int(num_pos_edges * negative_sampling_ratio)

        if self.edge_index.size() == self.edge_label_index.size() and (
            torch.sum(self.edge_index - self.edge_label_index) == 0
        ):
            # (train in 'all' mode)
            edge_index_all = self.edge_index
        else:
            edge_index_all = (
                torch.cat((self.edge_index, self.edge_label_index), -1)
            )

        if len(edge_index_all) > 0:
            if not torch.is_tensor(self.negative_edge):
                negative_edges_length = len(self.negative_edge)
                if negative_edges_length < num_neg_edges:
                    multiplicity = math.ceil(
                        num_neg_edges / negative_edges_length
                    )
                    self.negative_edge = self.negative_edge * multiplicity
                    self.negative_edge = self.negative_edge[:num_neg_edges]

                self.negative_edge = torch.tensor(
                    list(zip(*self.negative_edge))
                )
            if "negative_edge_idx" not in self:
                self.negative_edge_idx = 0

            negative_edges = self.negative_edge
            negative_edges_length = negative_edges.shape[1]

            if self.negative_edge_idx + num_neg_edges > negative_edges_length:
                negative_edges_begin = (
                    negative_edges[:, self.negative_edge_idx:]
                )
                negative_edges_end = negative_edges[
                    :, :self.negative_edge_idx
                    + num_neg_edges - negative_edges_length
                ]
                negative_edges = torch.cat(
                    [negative_edges_begin, negative_edges_end], axis=1
                )
            else:
                negative_edges = negative_edges[
                    :, self.negative_edge_idx:
                    self.negative_edge_idx + num_neg_edges
                ]
            self.negative_edge_idx = (
                (self.negative_edge_idx + num_neg_edges)
                % negative_edges_length
            )
        else:
            return torch.tensor([], dtype=torch.long)

        if not resample:
            if self.edge_label is None:
                # if label is not yet specified, use all ones for positives
                positive_label = torch.ones(num_pos_edges, dtype=torch.long)
                # if label is not yet specified, use all zeros for positives
                negative_label = torch.zeros(num_neg_edges, dtype=torch.long)
            else:
                # if label is specified, use max(positive_label) + 1
                # for negative labels
                positive_label = self.edge_label
                negative_label_val = torch.max(positive_label) + 1
                negative_label = (
                    negative_label_val
                    * torch.ones(num_neg_edges, dtype=torch.long)
                )
            self.edge_label = (
                torch.cat(
                    (positive_label, negative_label), -1
                ).type(torch.long)
            )

        self._num_positive_examples = num_pos_edges
        # append to edge_label_index
        self.edge_label_index = (
            torch.cat((self.edge_label_index, negative_edges), -1)
        )

    def _create_neg_sampling(
        self, negative_sampling_ratio: float, resample: bool = False
    ):
        r"""
        Create negative samples for link prediction,
        and changes the edge_label and edge_label_index accordingly (if already existed).

        Simplest link prediction has no label. It will be treated as binary classification.
        edge_label will be set to 1 for positives and 0 for negative examples.

        For link prediction that requires prediction of edge type, it will be a multi-class
        classification task.
        edge_label will be set to the (original label + 1) for positives and 0 for negative
        examples. Hence the number of prediction classes will be incremented by 1.
        In this case dataset.num_edge_labels should be called after split
        (which calls this function).

        Args:
            negative_sampling_ratio (float or int): ratio of negative sampling edges compared with the original edges.
            resample (boolean): whether should resample.
        """
        if resample and self._num_positive_examples is not None:
            # remove previous negative samples first
            # if self._num_positive_examples is None then no previous sampling was done
            self.edge_label_index = self.edge_label_index[
                :, : self._num_positive_examples
            ]
        num_pos_edges = self.edge_label_index.shape[-1]
        num_neg_edges = int(num_pos_edges * negative_sampling_ratio)

        if self.edge_index.size() == self.edge_label_index.size() and (
            torch.sum(self.edge_index - self.edge_label_index) == 0
        ):
            # (train in 'all' mode)
            edge_index_all = self.edge_index
        else:
            edge_index_all = (
                torch.cat((self.edge_index, self.edge_label_index), -1)
            )

        if len(edge_index_all) > 0:
            negative_edges = self.negative_sampling(
                edge_index_all, self.num_nodes, num_neg_edges
            )
        else:
            return torch.tensor([], dtype=torch.long)

        if not resample:
            if self.edge_label is None:
                # if label is not yet specified, use all ones for positives
                positive_label = torch.ones(num_pos_edges, dtype=torch.long)
                # if label is not yet specified, use all zeros for positives
                negative_label = torch.zeros(num_neg_edges, dtype=torch.long)
            else:
                # if label is specified, use max(positive_label) + 1
                # for negative labels
                positive_label = self.edge_label
                negative_label_val = torch.max(positive_label) + 1
                negative_label = (
                    negative_label_val
                    * torch.ones(num_neg_edges, dtype=torch.long)
                )
            self.edge_label = (
                torch.cat(
                    (positive_label, negative_label), -1
                ).type(torch.long)
            )

        self._num_positive_examples = num_pos_edges
        # append to edge_label_index
        self.edge_label_index = (
            torch.cat((self.edge_label_index, negative_edges), -1)
        )

    @staticmethod
    def add_node_attr(G, attr_name: str, node_attr):
        r"""
        Add node attribute into a NetworkX graph. Assumes that the
        `node_attr` ordering is the same as the node ordering in `G`.

        Args:
            G (NetworkX Graph): a NetworkX graph.
            attr_name (string): Name of the node
                attribute to set.
            node_attr (array_like): node attributes.
        """
        node_list = list(G.nodes)
        attr_dict = dict(zip(node_list, node_attr))
        nx.set_node_attributes(G, attr_dict, name=attr_name)

    @staticmethod
    def add_edge_attr(G, attr_name: str, edge_attr):
        r"""
        Add edge attribute into a NetworkX graph.

        Args:
            G (NetworkX Graph): a NetworkX graph.
            attr_name (string): Name of the edge
                attribute to set.
            edge_attr (array_like): edge attributes.
        """
        # TODO: parallel?
        edge_list = list(G.edges)
        attr_dict = dict(zip(edge_list, edge_attr))
        nx.set_edge_attributes(G, attr_dict, name=attr_name)

    @staticmethod
    def add_graph_attr(G, attr_name: str, graph_attr):
        r"""
        Add graph attribute into a NetworkX graph.

        Args:
            G (NetworkX Graph): a NetworkX graph.
            attr_name (string): Name of the graph attribute to set.
            graph_attr (scalar or array_like): graph attributes.
        """
        G.graph[attr_name] = graph_attr

    @staticmethod
    def pyg_to_graph(data, verbose: bool = False, fixed_split: bool = False, tensor_backend: bool = False):
        r"""
        Converts Pytorch Geometric data to a Graph object.

        Args:
            data (:class:`torch_geometric.data`): a Pytorch Geometric data.
            verbose: if print verbose warning
            fixed_split: if load fixed data split from PyG dataset
            tensor_backend: if using the tensor backend

        Returns:
            :class:`deepsnap.graph.Graph`: A new DeepSNAP :class:`deepsnap.graph.Graph` object.
        """
        # all fields in PyG Data object
        kwargs = {}
        kwargs["node_feature"] = data.x if "x" in data.keys else None
        kwargs["edge_feature"] = (
            data.edge_attr if "edge_attr" in data.keys else None
        )
        kwargs["node_label"], kwargs["edge_label"] = None, None
        kwargs["graph_feature"], kwargs["graph_label"] = None, None
        if kwargs["node_feature"] is not None and data.y.size(0) == kwargs[
            "node_feature"
        ].size(0):
            kwargs["node_label"] = data.y
        elif kwargs["edge_feature"] is not None and data.y.size(0) == kwargs[
            "edge_feature"
        ].size(0):
            kwargs["edge_label"] = data.y
        else:
            kwargs["graph_label"] = data.y

        if not tensor_backend:
            if data.is_directed():
                G = nx.DiGraph()
            else:
                G = nx.Graph()
            G.add_nodes_from(range(data.num_nodes))
            G.add_edges_from(data.edge_index.T.tolist())
        else:
            attributes = {}
            if not data.is_directed():
                row, col = data.edge_index
                mask = row < col
                row, col = row[mask], col[mask]
                edge_index = torch.stack([row, col], dim=0)
                edge_index = torch.cat(
                    [edge_index, torch.flip(edge_index, [0])], 
                    dim=1
                )
            else:
                edge_index = data.edge_index
            attributes["edge_index"] = edge_index

        # include other arguments that are in the kwargs of pyg data object
        keys_processed = ["x", "y", "edge_index", "edge_attr"]
        for key in data.keys:
            if key not in keys_processed:
                kwargs[key] = data[key]

        # we assume that edge-related and node-related features are defined
        # the same as in Graph._is_edge_attribute and Graph._is_node_attribute
        for key, value in kwargs.items():
            if value is None:
                continue
            if Graph._is_node_attribute(key):
                if not tensor_backend:
                    Graph.add_node_attr(G, key, value)
                else:
                    attributes[key] = value
            elif Graph._is_edge_attribute(key):
                # TODO: make sure the indices of edge attributes are same with edge_index
                if not tensor_backend:
                    # the order of edge attributes is consistent with edge index
                    Graph.add_edge_attr(G, key, value)
                else:
                    attributes[key] = value
            elif Graph._is_graph_attribute(key):
                if not tensor_backend:
                    Graph.add_graph_attr(G, key, value)
                else:
                    attributes[key] = value
            else:
                if verbose:
                    print(f"Index fields: {key} ignored.")

        if fixed_split:
            masks = ["train_mask", "val_mask", "test_mask"]
            if not tensor_backend:
                graph = Graph(G)
            else:
                graph = Graph(**attributes)
            graphs = []
            for mask in masks:
                if mask in kwargs:
                    graph_new = copy.copy(graph)
                    graph_new.node_label_index = (
                        torch.nonzero(data[mask]).squeeze()
                    )
                    graph_new.node_label = (
                        graph_new.node_label[graph_new.node_label_index]
                    )
                    graphs.append(graph_new)
            return graphs
        else:
            if not tensor_backend:
                return Graph(G)
            else:
                return Graph(**attributes)

    @staticmethod
    def raw_to_graph(data):
        r"""
        Write other methods for user to import their own data format and
        make sure all attributes of G are scalar/torch.tensor. ``Not implemented``.
        """
        raise NotImplementedError

    @staticmethod
    def negative_sampling(edge_index, num_nodes=None, num_neg_samples=None):
        r"""Samples random negative edges of a graph given by :attr:`edge_index`.

        Args:
            edge_index (:class:`torch.LongTensor`): The edge indices.
            num_nodes (int, optional): The number of nodes, *i.e.*
                :obj:`max_val + 1` of :attr:`edge_index`. (default: :obj:`None`)
            num_neg_samples (int, optional): The number of negative samples to
                return. If set to :obj:`None`, will try to return a negative edge
                for every positive edge. (default: :obj:`None`)
            force_undirected (bool, optional): If set to :obj:`True`, sampled
                negative edges will be undirected. (default: :obj:`False`)

        :rtype: :class:`torch.LongTensor`
        """
        num_neg_samples = min(
            num_neg_samples, num_nodes * num_nodes - edge_index.size(1)
        )

        rng = range(num_nodes ** 2)
        # idx = N * i + j
        idx = (edge_index[0] * num_nodes + edge_index[1]).to("cpu")

        perm = torch.tensor(random.sample(rng, num_neg_samples))
        mask = torch.from_numpy(np.isin(perm, idx)).to(torch.bool)
        rest = mask.nonzero().view(-1)
        while rest.numel() > 0:  # pragma: no cover
            tmp = torch.tensor(random.sample(rng, rest.size(0)))
            mask = torch.from_numpy(np.isin(tmp, idx)).to(torch.bool)
            perm[rest] = tmp
            rest = rest[mask.nonzero().view(-1)]

        row = perm // num_nodes
        col = perm % num_nodes
        neg_edge_index = torch.stack([row, col], dim=0).long()

        return neg_edge_index.to(edge_index.device)
