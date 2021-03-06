import math
import copy
import random
import torch
import networkx as nx
import numpy as np
from deepsnap.graph import Graph
from typing import (
   Dict,
   List,
   Union,
)
import warnings


class HeteroGraph(Graph):
    r"""
    A plain python object modeling a heterogeneous graph with various
    attributes (String node type is required for the HeteroGraph).

    Args:
        G (:class:`networkx.classes.graph`): The NetworkX graph object which contains features
             and labels for each node type of edge type.
        **kwargs: keyworded argument list with keys such as :obj:`"node_feature"`, :obj:`"node_label"`
            and corresponding attributes.
    """
    def __init__(self, G=None, **kwargs):
        # TODO: merge similar parts with base class
        # super(HeteroGraph, self).__init__()
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
                    "A dictionary of tensor of edge_index is required by "
                    "using the tensor backend."
                )
            # check for undirected edge_index format
            if not self.directed:
                for message_type in self.edge_index:
                    edge_index_length = self.edge_index[message_type].shape[1]
                    edge_index_first_half, _ = (
                            torch.sort(
                                self.edge_index
                                [message_type][:, :int(edge_index_length / 2)]
                            )
                    )
                    edge_index_second_half, _ = (
                            torch.sort(
                                self.edge_index
                                [message_type][:, int(edge_index_length / 2):]
                            )
                    )
                    if not torch.equal(
                        edge_index_first_half,
                        torch.flip(edge_index_second_half, [0])
                    ):
                        raise ValueError(
                            "In tensor backend mode with undirected graph, "
                            "the user provided edge_index for each "
                            "message_type should contain "
                            "undirected edges for both directions."
                            "the first half of edge_index should contain "
                            "unique edges in one direction and the second "
                            "half of edge_index should contain the same set "
                            "of unique edges of another direction."
                            "The corresponding message_type of edge_index "
                            f"that fails this check is: {message_type}."
                        )

        if G is not None or kwargs:
            self._update_tensors(init=True)
        self._num_positive_examples = None

    @property
    def node_types(self):
        r"""
        Return list of node types in the heterogeneous graph.
        """
        return list(self[self._node_related_key].keys())

    @property
    def edge_types(self):
        r"""
        Return list of edge types in the heterogeneous graph.
        """
        edge_type_set = set()
        for _, edge_type, _ in self["edge_index"].keys():
            edge_type_set.add(edge_type)
        return list(edge_type_set)

    @property
    def message_types(self):
        r"""
        Return the list of message types `(src_node_type, edge_type, end_node_type)`
        in the heterogeneous graph.
        """
        return list(self["edge_index"].keys())

    def num_nodes(self, node_type: Union[str, List[str]] = None):
        r"""
        Return number of nodes for a node type or list of node types.

        Args:
            node_type (str or list): Specified node type(s).

        Returns:
            int or list: The number of nodes for a node type or list of node types.
        """
        if node_type is None:
            node_type = self.node_types
        if (
            isinstance(node_type, str)
            or isinstance(node_type, int)
            or isinstance(node_type, float)
        ):
            if node_type in self[self._node_related_key]:
                return len(self[self._node_related_key][node_type])
            else:
                raise ValueError(
                    "Node type does not exist in stored node feature."
                )
        if isinstance(node_type, list):
            if not all(
                node_type_i in self[self._node_related_key] for
                node_type_i in node_type
            ):
                raise ValueError(
                    "Some node types do not exist in stored node feature."
                )
            else:
                num_nodes_dict = {}
                for node_type_i in node_type:
                    num_nodes_dict[node_type_i] = (
                        len(self[self._node_related_key][node_type_i])
                    )
                return num_nodes_dict
        else:
            raise TypeError("Node types have unexpected type.")

    def num_node_features(self, node_type: Union[str, List[str]] = None):
        r"""
        Return the node feature dimension of specified node type.

        Returns:
            int: The node feature dimension for specified node type.
        """
        if "node_feature" not in self:
            return 0

        if node_type is None:
            node_type = self.node_types
        if (
            isinstance(node_type, str)
            or isinstance(node_type, int)
            or isinstance(node_type, float)
        ):
            if node_type in self["node_feature"]:
                return self.get_num_dims(
                    "node_feature", node_type, as_label=False
                )
            else:
                raise ValueError(
                    "Node type does not exist in stored node feature."
                )
        if isinstance(node_type, list):
            if not all(
                node_type_i in self["node_feature"] for
                node_type_i in node_type
            ):
                raise ValueError(
                    "Some node types do not exist in stored node feature."
                )
            else:
                num_nodes_feature_dict = {}
                for node_type_i in node_type:
                    num_nodes_feature_dict[node_type_i] = (
                        self.get_num_dims(
                            "node_feature", node_type_i, as_label=False
                        )
                    )
                return num_nodes_feature_dict
        else:
            raise TypeError("Node types have unexpected type.")

    def num_node_labels(self, node_type: Union[str, List[str]] = None):
        r"""
        Return the number of node labels.

        Returns:
            int: Number of node labels for specified node type.
        """
        if "node_label" not in self:
            return 0

        if node_type is None:
            node_type = self.node_types
        if (
            isinstance(node_type, str)
            or isinstance(node_type, int)
            or isinstance(node_type, float)
        ):
            if node_type in self["node_label"]:
                return self.get_num_dims(
                    "node_label", node_type, as_label=True
                )
            else:
                raise ValueError(
                    "Node type does not exist in stored node feature."
                )
        if isinstance(node_type, list):
            if not all(
                node_type_i in self["node_label"] for
                node_type_i in node_type
            ):
                raise ValueError(
                    "Some node types do not exist in stored node feature."
                )
            else:
                num_nodes_label_dict = {}
                for node_type_i in node_type:
                    num_nodes_label_dict[node_type_i] = (
                        self.get_num_dims(
                            "node_label", node_type_i, as_label=True
                        )
                    )

                return num_nodes_label_dict
        else:
            raise TypeError("Node types have unexpected type.")

    def num_edges(
        self,
        message_type: Union[tuple, List[tuple]] = None
    ):
        r"""
        Return number of edges for a edge type or list of edgs types.

        Args:
            edge_type (str or list): Specified edge type(s).

        Returns:
            int or list: The number of edges for a edge type or list of edge types.
        """

        if "edge_index" not in self:
            raise ValueError("Edge indices is not available")
        if message_type is None:
            message_type = self.message_types
        if isinstance(message_type, tuple):
            if message_type in self["edge_index"]:
                num_edge = self["edge_index"][message_type].size(1)
                if self.is_undirected():
                    num_edge = int(num_edge / 2)
                return num_edge
            else:
                raise ValueError(
                    "Edge type does not exist in stored edge feature."
                )
        if isinstance(message_type, list):
            if not all(
                isinstance(message_type_i, tuple)
                for message_type_i in message_type
            ):
                raise ValueError("Edge type must be tuple.")
            if not all(
                message_type_i in self["edge_index"]
                for message_type_i in message_type
            ):
                raise ValueError(
                    "Some edge types do not exist in stored edge feature."
                )
            else:
                num_edges_dict = {}
                for message_type_i in message_type:
                    num_edges_type_i = (
                        self["edge_index"][message_type_i].size(1)
                    )
                    if self.is_undirected():
                        num_edges_type_i = int(num_edges_type_i / 2)
                    num_edges_dict[message_type_i] = num_edges_type_i
                return num_edges_dict
        else:
            raise TypeError("Edge type must be tuple or list of tuple")

    def num_edge_labels(
        self,
        message_type: Union[tuple, List[tuple]] = None
    ):
        r"""
        Return the number of edge labels.

        Returns:
            int: Number of edge labels for specified edge type.
        """

        if "edge_label" not in self:
            return 0
        if "edge_index" not in self:
            raise ValueError("Edge indices is not available")
        if message_type is None:
            message_type = self.message_types
        if isinstance(message_type, tuple):
            if message_type in self["edge_index"]:
                return self.get_num_dims("edge_label", message_type, as_label=True)
            else:
                raise ValueError(
                    "Edge type does not exist in stored edge feature."
                )
        if isinstance(message_type, list):
            if not all(
                isinstance(message_type_i, tuple)
                for message_type_i in message_type
            ):
                raise ValueError("Edge type must be tuple.")
            if not all(
                message_type_i in self["edge_index"]
                for message_type_i in message_type
            ):
                raise ValueError(
                    "Some edge types do not exist in stored edge feature."
                )
            else:
                num_edges_label_dict = {}
                for message_type_i in message_type:
                    num_edges_label_dict[message_type_i] = (
                        self.get_num_dims(
                            "edge_label", message_type_i, as_label=True
                        )
                    )
                return num_edges_label_dict
        else:
            raise TypeError("Edge type must be tuple or list of tuple")

    def num_edge_features(
        self,
        message_type: Union[tuple, List[tuple]] = None
    ):
        r"""
        Return the edge feature dimension of specified edge type.

        Returns:
            int: The edge feature dimension for specified edge type.
        """

        if "edge_feature" not in self:
            return 0

        if "edge_index" not in self:
            raise ValueError("Edge indices is not available")
        if message_type is None:
            message_type = self.message_types
        if isinstance(message_type, tuple):
            if message_type in self["edge_index"]:
                return self.get_num_dims(
                    "edge_feature", message_type, as_label=False
                )
            else:
                raise ValueError(
                    "Edge type does not exist in stored edge feature."
                )
        if isinstance(message_type, list):
            if not all(
                isinstance(message_type_i, tuple)
                for message_type_i in message_type
            ):
                raise ValueError("Edge type must be tuple.")
            if not all(
                message_type_i in self["edge_index"]
                for message_type_i in message_type
            ):
                raise ValueError(
                    "Some edge types do not exist in stored edge feature."
                )
            else:
                num_edges_feature_dict = {}
                for message_type_i in message_type:
                    num_edges_feature_dict[message_type_i] = (
                        self.get_num_dims(
                            "edge_feature", message_type_i, as_label=False
                        )
                    )

                return num_edges_feature_dict
        else:
            raise TypeError("Edge type must be tuple or list of tuple")

    def _get_node_type(self, node_dict: Dict):
        r"""
        Returns the node type of a node in its dict.

        Args:
            node_dict (dictionary): The node dictionary.

        Returns:
            the string of the node type: node type.
        """
        if "node_type" not in node_dict:
            return None
        return node_dict["node_type"]

    def _get_edge_type(self, edge_dict: Dict):
        r"""
        Similar to the `_get_node_type`
        """
        if "edge_type" not in edge_dict:
            return None
        return edge_dict["edge_type"]

    def _convert_to_graph_index(
        self,
        index: int,
        obj_type,
        mapping_type="node"
    ):
        r"""
        Reverse operation of `_convert_to_tensor_index`
        """
        if mapping_type == "node":
            mapping = self.node_to_graph_mapping
        elif mapping_type == "edge":
            mapping = self.edge_to_graph_mapping
        else:
            raise ValueError("Mapping type should be node or edge.")
        if obj_type not in mapping:
            raise ValueError("Node/edge type not in the graph.")
        return torch.index_select(mapping[obj_type], 0, index)

    def _convert_to_tensor_index(self, index: int, mapping_type="node"):
        r"""
        Returns specified type of index tensor.

        Args:
            index(tensor): the index tensor you want to transform.
            mapping_type(string): specify which mapping node or edge.

        Returns:
            index tensor.
        """
        if mapping_type == "node":
            mapping = self.node_to_tensor_mapping
        elif mapping_type == "edge":
            mapping = self.edge_to_tensor_mapping
        else:
            raise ValueError("Mapping type should be node or edge.")
        return torch.index_select(mapping, 0, index)

    def _get_node_attributes(self, key: str):
        r"""
        Returns the node attributes in the graph. Multiple attributes will be stacked.

        Args:
            key(string): the name of the attributes to return.

        Returns:
            a dictionary of node type to torch.tensor: node attributes.
        """
        attributes = {}
        indices = None
        if key == "node_type":
            indices = {}

        for node_idx, (_, node_dict) in enumerate(self.G.nodes(data=True)):
            if key in node_dict:
                node_type = self._get_node_type(node_dict)
                if node_type not in attributes:
                    attributes[node_type] = []
                attributes[node_type].append(node_dict[key])
                if indices is not None:
                    if node_type not in indices:
                        indices[node_type] = []
                    # use range(0 ~ num_nodes) as the graph node indices
                    indices[node_type].append(node_idx)

        if len(attributes) == 0:
            return None

        for node_type, val in attributes.items():
            if torch.is_tensor(attributes[node_type][0]):
                attributes[node_type] = torch.stack(val, dim=0)
            elif isinstance(attributes[node_type][0], float):
                attributes[node_type] = torch.tensor(val, dtype=torch.float)
            elif isinstance(attributes[node_type][0], int):
                attributes[node_type] = torch.tensor(val, dtype=torch.long)

        if indices is not None:
            node_to_tensor_mapping = (
                torch.zeros([self.G.number_of_nodes(), ], dtype=torch.int64)
            )
            for node_type in indices:
                # row 0 for graph index, row 1 for tensor index
                indices[node_type] = (
                    torch.tensor(indices[node_type], dtype=torch.int64)
                )
                node_to_tensor_mapping[indices[node_type]] = (
                    torch.arange(len(indices[node_type]), dtype=torch.int64)
                )
            self.node_to_graph_mapping = indices
            self.node_to_tensor_mapping = node_to_tensor_mapping

        return attributes

    def _get_edge_attributes(self, key: str):
        r"""
        Similar to the `_get_node_attributes`
        """
        attributes = {}
        indices = None
        # TODO: what if there is no edge_feature ?
        # TODO: suspect edge_to_tensor_mapping and edge_to_graph_mapping not useful
        if key == "edge_type":
            indices = {}
        for edge_idx, (head, tail, edge_dict) in enumerate(
            self.G.edges(data=True)
        ):
            if key in edge_dict:
                head_type = self.G.nodes[head]["node_type"]
                tail_type = self.G.nodes[tail]["node_type"]
                edge_type = self._get_edge_type(edge_dict)
                message_type = (head_type, edge_type, tail_type)
                if message_type not in attributes:
                    attributes[message_type] = []
                attributes[message_type].append(edge_dict[key])
                if indices is not None:
                    if message_type not in indices:
                        indices[message_type] = []
                    indices[message_type].append(edge_idx)

        if len(attributes) == 0:
            return None

        for message_type, val in attributes.items():
            if torch.is_tensor(attributes[message_type][0]):
                attributes[message_type] = torch.stack(val, dim=0)
            elif isinstance(attributes[message_type][0], float):
                attributes[message_type] = torch.tensor(val, dtype=torch.float)
            elif isinstance(attributes[message_type][0], int):
                attributes[message_type] = torch.tensor(val, dtype=torch.long)
            elif isinstance(attributes[message_type][0], str) and key == "edge_type":
                continue
            else:
                raise TypeError(f"Unknown type {key} in edge attributes.")
            if self.is_undirected() and key != "edge_type":
                attributes[message_type] = torch.cat(
                    [attributes[message_type], attributes[message_type]], dim=0
                )

        if indices is not None:
            edge_to_tensor_mapping = (
                torch.zeros([self.G.number_of_edges(), ], dtype=torch.int64)
            )
            for message_type in indices:
                indices[message_type] = (
                    torch.tensor(indices[message_type], dtype=torch.int64)
                )
                edge_to_tensor_mapping[indices[message_type]] = (
                    torch.arange(len(indices[message_type]), dtype=torch.int64)
                )
            self.edge_to_graph_mapping = indices
            self.edge_to_tensor_mapping = edge_to_tensor_mapping

        return attributes

    def _update_index(self, init: bool = False):
        r"""
        Currently store the edge_index and edge_indices for each edge_type
        """
        if self.G is not None:
            keys = list(self.G.nodes)
            vals = range(sum(self.num_nodes().values()))
            mapping = dict(zip(keys, vals))
            self.G = nx.relabel_nodes(self.G, mapping, copy=True)
            self.edge_index = (
                self._edge_to_index(
                    list(self.G.edges(data=True)),
                    list(self.G.nodes(data=True)),
                )
            )
        else:
            mapping = {x: x for x in range(sum(self.num_nodes().values()))}
        if init:
            self.edge_label_index = copy.deepcopy(self.edge_index)
            self.node_label_index = {}
            for node_type in self.node_types:
                self.node_label_index[node_type] = (
                    torch.arange(
                        self.num_nodes(node_type),
                        dtype=torch.long
                    )
                )

            self._custom_update()
            if self.task is not None:
                if self.general_splits is not None:
                    if self.task == "node":
                        for i in range(len(self.general_splits)):
                            nodes = self.general_splits[i]

                            if isinstance(nodes[0], tuple):
                                nodes = [
                                    (mapping[node[0]], node[-1])
                                    for node in nodes
                                ]
                            else:
                                nodes = [
                                    (
                                        mapping[node[0]],
                                        self.G.nodes[mapping[node[0]]]
                                    )
                                    for node in nodes
                                ]
                            type_nodes = {}
                            for node in nodes:
                                node_type = node[-1]["node_type"]
                                if node_type not in type_nodes:
                                    type_nodes[node_type] = []
                                type_nodes[node_type].append(node[0])
                            node_label_index = {
                                node_type: self._convert_to_tensor_index(
                                    torch.tensor(
                                        type_nodes[node_type],
                                        dtype=torch.long
                                    )
                                )
                                for node_type in type_nodes
                            }
                            self.general_splits[i] = node_label_index

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

    def _edge_to_index(self, edges, nodes):
        r"""
        Make edge_index from networkx Graph Nodes and Edges.
        """
        edge_index = {}
        nodes_dict = {}
        for node in nodes:
            nodes_dict[node[0]] = node[1]["node_type"]

        for idx, edge in enumerate(edges):
            if isinstance(edge_index, dict):
                edge_type = self._get_edge_type(edge[-1])
                head_type = nodes_dict[edge[0]]
                tail_type = nodes_dict[edge[1]]
                message_type = (head_type, edge_type, tail_type)

                if message_type not in edge_index:
                    edge_index[message_type] = []
                edge_index[message_type].append((edge[0], edge[1]))

        for key in edge_index:
            edge_index[key] = torch.tensor(edge_index[key])

        if self.is_undirected():
            for key in edge_index:
                edge_index[key] = torch.cat(
                    [edge_index[key], torch.flip(edge_index[key], [1])],
                    dim=0,
                )

        for key in edge_index:
            permute_tensor = edge_index[key].permute(1, 0)
            source_node_index = (
                self._convert_to_tensor_index(permute_tensor[0])
            )
            target_node_index = (
                self._convert_to_tensor_index(permute_tensor[1])
            )
            edge_index[key] = (
                torch.stack([source_node_index, target_node_index])
            )

        return edge_index

    @staticmethod
    def _is_edge_attribute(key: str) -> bool:
        r"""
        Check whether an attribute is a edge attribute.
        """
        # could be feature, label, etc.
        return "edge" in key and "index" not in key and "type" not in key

    @staticmethod
    def _is_node_attribute(key: str) -> bool:
        r"""
        Check whether an attribute is a node attribute.
        """
        # could be feature, label, etc.
        return "node" in key and "index" not in key and "type" not in key

    def _is_valid(self):
        r"""
        Check validity.
        """
        for key in self.keys:
            if self._is_node_attribute(key):
                num_nodes = 0
                if key != "node_to_tensor_mapping":
                    for node_type in self[key]:
                        num_nodes += self[key][node_type].size(0)
                else:
                    num_nodes = self[key].size(0)
                assert (
                    sum(self.num_nodes().values()) == num_nodes
                ), f"key {key} is not valid"
            if self._is_edge_attribute(key):
                num_edges = 0
                if key != "edge_to_tensor_mapping":
                    for edge_type in self[key]:
                        num_edges += self[key][edge_type].size(0)
                else:
                    num_edges = self[key].size(0)
                assert (
                    sum(self.num_edges().values()) == num_edges
                    or self.num_edges * 2 == num_edges
                ), f"key {key} is not valid"

    def get_num_dims(self, key, obj_type, as_label: bool = False) -> int:
        r"""
        Returns the number of dimensions for one graph/node/edge property
        for specified types.

        Args:
            key (str): The choosing property.
            obj_type: Node or edge type.
            as_label (bool): If as_label, treat the tensor as labels.
        """
        if as_label:
            # treat as label
            if self[key] is not None and obj_type in self[key]:
                if self[key][obj_type].dtype == torch.long:
                    # classification label
                    return torch.max(self[key][obj_type]).item() + 1
                else:
                    # regression label
                    if len(self[key][obj_type].shape) == 1:
                        return 1
                    else:
                        return self.edge_label[obj_type].shape[1]
            else:
                return 0
        else:
            # treat as feature
            if self[key][obj_type] is not None:
                return self[key][obj_type].shape[1]
            else:
                return 0

    def _create_label_link_pred(self, graph, edges, nodes=None):
        r"""
        Create edge label and the corresponding label_index (edges) fo  r link prediction.

        Modifies the graph argument by setting the fields edge_label_i  ndex and edge_label.
        """
        if self.G is not None:
            graph.edge_label_index = (
                self._edge_to_index(edges, nodes)
            )
            graph.edge_label = self._get_edge_attributes_by_key(
                edges,
                "edge_label",
            )
            graph._objective_edges = edges
        else:
            edge_label_index = {}
            for message_type in edges:
                edge_label_index[message_type] = torch.index_select(
                    self.edge_index[message_type], 1, edges[message_type]
                )

            # TODO: add unit test
            # TODO: deepcopy ?
            graph._objective_edges = edge_label_index

            if self.is_undirected():
                for message_type in edge_label_index:
                    edge_label_index[message_type] = torch.cat(
                        [
                            edge_label_index[message_type],
                            torch.flip(edge_label_index[message_type], [0])
                        ],
                        dim=1
                    )
                    # edge_label should probably also be duplicated here

            graph.edge_label_index = edge_label_index
            graph.edge_label = (
                self._get_edge_attributes_by_key_tensor(edges, "edge_label")
            )

    def _get_edge_attributes_by_key_tensor(self, edge_index, key: str):
        r"""
        Extract the edge attributes indicated by edge_index in tensor backend.
        """
        if not (
            isinstance(edge_index, dict)
            and all(
                isinstance(message, tuple)
                and torch.is_tensor(edge_index_message)
                for message, edge_index_message in edge_index.items()
            )
        ):
            raise TypeError("edge_index in not in the correct format.")
        if key == "edge_index":
            raise ValueError(
                "edge_index cannot be selected."
            )
        if key not in self.keys or not isinstance(self[key], dict):
            return None

        attributes = {}
        for message_type in edge_index:
            attributes[message_type] = torch.index_select(
                self[key][message_type], 0, edge_index[message_type]
            )
            if self.is_undirected():
                attributes[message_type] = torch.cat(
                    [attributes[message_type], attributes[message_type]], dim=0
                )

        return attributes

    def _get_edge_attributes_by_key(self, edges, key: str):
        r"""
        List of G.edges to torch tensor for key, which dimension [num_edges x key_dim].

        Only the selected edges' attributes are extracted.
        """
        if len(edges) == 0:
            raise ValueError(
                "in _get_edge_attributes_by_key, "
                "len(edges) must be larger than 0"
            )
        if not isinstance(edges[0][-1], dict) or key not in edges[0][-1]:
            return None

        attributes = {}
        for edge in edges:
            head_type = self.G.nodes[edge[0]]["node_type"]
            tail_type = self.G.nodes[edge[1]]["node_type"]
            edge_type = edge[-1]["edge_type"]
            message_type = (head_type, edge_type, tail_type)
            if message_type not in attributes:
                attributes[message_type] = []
            attributes[message_type].append(edge[-1][key])

        for message_type in attributes:
            if torch.is_tensor(attributes[message_type][0]):
                attributes[message_type] = torch.stack(
                    attributes[message_type], dim=0
                )
            elif isinstance(attributes[message_type][0], float):
                attributes[message_type] = torch.tensor(
                    attributes[message_type], dtype=torch.float
                )
            elif isinstance(attributes[message_type][0], int):
                attributes[message_type] = torch.tensor(
                    attributes[message_type], dtype=torch.long
                )
            if self.is_undirected():
                attributes[message_type] = torch.cat(
                    [attributes[message_type], attributes[message_type]], dim=0
                )

        return attributes

    def _split_node(self, split_types: List[str], split_ratio: float):
        r"""
        Split the graph into len(split_ratio) graphs for node prediction.
        Internally this splits node indices, and the model will only compute
        loss for the embedding of
        nodes in each split graph.
        In node classification, the whole graph is observed in train/val/test
        Only split over node_label_index
        """
        if split_types is None:
            split_types = self.node_types
        if not isinstance(split_types, list):
            raise TypeError("Split_types must be string or list of string.")
        if not all(
            [
                split_type in self.node_types
                for split_type in split_types
            ]
        ):
            raise ValueError(
                "Split type in split_types must exist in "
                "self.node_label_index."
            )
        if not all(
            num_node_type >= len(split_ratio)
            for split_type, num_node_type
            in self.num_nodes(split_types).items()
        ):
            raise ValueError(
                "In _split_node num of nodes of a specific type is smaller "
                "than the number of splitted parts."
            )
        split_graphs = []
        split_offsets = {}
        split_type_nodes_lengths = {}
        split_type_nodes = {}

        for i, split_ratio_i in enumerate(split_ratio):
            graph_new = copy.copy(self)
            node_label_index = {}
            node_label = {}
            for split_type in split_types:
                if split_type not in split_offsets:
                    split_offsets[split_type] = 0
                    split_type_nodes_lengths[split_type] = (
                        len(graph_new.node_label_index[split_type])
                    )
                    split_type_nodes[split_type] = (
                        graph_new.node_label_index[split_type][
                            torch.randperm(
                                split_type_nodes_lengths[split_type]
                            )
                        ]
                    )
                split_offset = split_offsets[split_type]
                split_type_nodes_length = split_type_nodes_lengths[split_type]
                split_type_node = split_type_nodes[split_type]

                # perform `secure split` s.t. guarantees all splitted subgraph
                # of a split type contains at least one node.
                if i != len(split_ratio) - 1:
                    num_split_i = (
                        1 +
                        int(
                            split_ratio_i *
                            (split_type_nodes_length - len(split_ratio))
                        )
                    )
                    nodes_split_i = (
                        split_type_node[
                            split_offset: split_offset + num_split_i
                        ]
                    )
                    split_offsets[split_type] += num_split_i
                else:
                    nodes_split_i = split_type_node[split_offset:]

                node_label_index[split_type] = nodes_split_i
                node_label[split_type] = (
                    self.node_label[split_type][nodes_split_i]
                )

            # add the non-splitted types
            for node_type in self.node_types:
                if node_type not in split_types:
                    node_label_index[node_type] = (
                        self.node_label_index[node_type]
                    )

            graph_new.node_label_index = node_label_index
            graph_new.node_label = node_label
            split_graphs.append(graph_new)

        return split_graphs

    def _split_edge(self, split_types: List[tuple], split_ratio: float):
        r"""
        Split the graph into len(split_ratio) graphs for node prediction.
        Internally this splits node indices, and the model will only compute
        loss for the embedding of nodes in each split graph.
        In edge classification, the whole graph is observed in train/val/test.
        Only split over edge_label_index.
        """
        if split_types is None:
            split_types = self.message_types
        if not isinstance(split_types, list):
            raise TypeError("Split_types must be string or list of string.")
        if not all(
            [
                split_type in self.message_types
                for split_type in split_types
            ]
        ):
            raise ValueError(
                "Split type in split_types must exist in "
                "self.node_label_index."
            )
        if not all(
            num_edge_type >= len(split_ratio)
            for split_type, num_edge_type
            in self.num_edges(split_types).items()
        ):
            raise ValueError(
                "In _split_edge num of edges of a specific type is smaller "
                "than the number of splitted parts."
            )

        split_graphs = []
        split_offsets = {}
        split_type_edges_lengths = {}
        split_type_edges = {}
        split_type_edges_label = {}

        for i, split_ratio_i in enumerate(split_ratio):
            graph_new = copy.copy(self)
            edge_label_index = {}
            edge_label = {}
            for split_type in split_types:
                if split_type not in split_offsets:
                    split_offsets[split_type] = 0
                    split_type_edges_lengths[split_type] = (
                        graph_new.edge_label_index[split_type].shape[1]
                    )
                    rand_idx_type = (
                        torch.randperm(split_type_edges_lengths[split_type])
                    )
                    split_type_edges[split_type] = (
                        graph_new.edge_label_index[split_type][
                            :, rand_idx_type
                        ]
                    )
                    split_type_edges_label[split_type] = (
                        graph_new.edge_label[split_type][rand_idx_type]
                    )

                split_offset = split_offsets[split_type]
                split_type_edges_length = split_type_edges_lengths[split_type]
                split_type_edge = split_type_edges[split_type]
                split_type_edge_label = split_type_edges_label[split_type]

                # perform `secure split` s.t. guarantees all splitted subgraph
                # of a split type contains at least one edge.
                if i != len(split_ratio) - 1:
                    num_split_i = (
                        1 +
                        int(
                            split_ratio_i *
                            (split_type_edges_length - len(split_ratio))
                        )
                    )
                    edges_split_i = (
                        split_type_edge[
                            :, split_offset: split_offset + num_split_i
                        ]
                    )
                    edges_label_split_i = (
                        split_type_edge_label[
                            split_offset: split_offset + num_split_i
                        ]
                    )
                    split_offsets[split_type] += num_split_i
                else:
                    edges_split_i = split_type_edge[:, split_offset:]
                    edges_label_split_i = (
                        split_type_edge_label[split_offset:]
                    )

                edge_label_index[split_type] = edges_split_i
                edge_label[split_type] = edges_label_split_i

            # add the non-splitted types
            for edge_type in self.message_types:
                if edge_type not in split_types:
                    edge_label_index[edge_type] = (
                        self.edge_label_index[edge_type]
                    )
                    edge_label[edge_type] = (
                        self.edge_label[edge_type]
                    )

            graph_new.edge_label_index = edge_label_index
            graph_new.edge_label = edge_label
            split_graphs.append(graph_new)

        return split_graphs

    def _custom_split_link_pred_disjoint(self):
        # TODO: add tensor backend support
        objective_edges = self.disjoint_split

        nodes_dict = {}
        for node in self.G.nodes(data=True):
            nodes_dict[node[0]] = node[1]["node_type"]

        edges_dict = {}
        objective_edges_dict = {}

        for edge in self.G.edges:
            edge_dict = self.G.edges[edge]
            edge_type = edge_dict["edge_type"]
            head_type = nodes_dict[edge[0]]
            tail_type = nodes_dict[edge[1]]
            message_type = (head_type, edge_type, tail_type)
            if message_type not in edges_dict:
                edges_dict[message_type] = []
            if len(edge) == 2:
                edges_dict[message_type].append((edge[0], edge[1], edge_dict))
            elif len(edge) == 3:
                edges_dict[message_type].append(
                    (edge[0], edge[1], edge[2], edge_dict)
                )
            else:
                raise ValueError("Each edge has more than 3 indices.")

        for edge in objective_edges:
            edge_type = edge[-1]["edge_type"]
            head_type = nodes_dict[edge[0]]
            tail_type = nodes_dict[edge[1]]
            message_type = (head_type, edge_type, tail_type)
            if message_type not in objective_edges_dict:
                objective_edges_dict[message_type] = []
            objective_edges_dict[message_type].append(edge)

        message_edges = []
        for edge_type in edges_dict:
            if edge_type in objective_edges_dict:
                edges_no_info = [edge[:-1] for edge in edges_dict[edge_type]]
                objective_edges_no_info = [
                    edge[:-1] for edge in objective_edges_dict[edge_type]
                ]
                message_edges_no_info = (
                    set(edges_no_info) - set(objective_edges_no_info)
                )

                for edge in message_edges_no_info:
                    if len(edge) == 2:
                        message_edges.append(
                            (
                                edge[0], edge[1],
                                self.G.edges[(edge[0], edge[1])]
                            )
                        )
                    elif len(edge) == 3:
                        message_edges.append(
                            (
                                edge[0], edge[1], edge[2],
                                self.G.edges[(edge[0], edge[1], edge[2])]
                            )
                        )
                    else:
                        raise ValueError("Each edge has more than 3 indices.")
            else:
                message_edges += edges_dict[edge_type]

        # update objective edges
        for edge_type in edges_dict:
            if edge_type not in objective_edges_dict:
                objective_edges += edges_dict[edge_type]

        graph_train = HeteroGraph(
            self._edge_subgraph_with_isonodes(
                self.G,
                message_edges,
            ),
            negative_edges=self.negative_edges
        )

        graph_train._create_label_link_pred(
            graph_train,
            objective_edges,
            list(graph_train.G.nodes(data=True))
        )

        return graph_train

    def _custom_split_link_pred(self):
        # TODO: add tensor backend support
        split_num = len(self.general_splits)
        split_graph = []
        edges_train = self.general_splits[0]
        edges_val = self.general_splits[1]

        graph_train = HeteroGraph(
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
            graph_test = HeteroGraph(
                self._edge_subgraph_with_isonodes(
                    self.G,
                    edges_train + edges_val
                ),
                negative_edges=(
                    self.negative_edges
                )
            )

        graph_train._create_label_link_pred(
            graph_train,
            edges_train,
            list(graph_train.G.nodes(data=True))
        )
        graph_val._create_label_link_pred(
            graph_val,
            edges_val,
            list(graph_val.G.nodes(data=True))
        )

        if split_num == 3:
            graph_test._create_label_link_pred(
                graph_test,
                edges_test,
                list(graph_test.G.nodes(data=True))
            )

        split_graph.append(graph_train)
        split_graph.append(graph_val)
        if split_num == 3:
            split_graph.append(graph_test)

        return split_graph

    def split_link_pred(
        self,
        split_types: List[tuple],
        split_ratio: Union[float, List[float]],
        edge_split_mode: str = "exact",
    ):
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
        if split_types is None:
            split_types = self.message_types
        if not isinstance(split_types, list):
            raise TypeError("Split_types must be string or list of string.")
        if not all(
            [
                split_type in self.message_types
                for split_type in split_types
            ]
        ):
            raise ValueError(
                "Split type in split_types must exist in self.node_label_index"
            )
        if isinstance(split_ratio, float):
            split_ratio = [split_ratio, 1 - split_ratio]
        if len(split_ratio) < 2 or len(split_ratio) > 3:
            raise ValueError("Unrecoginzed number of splits")

        if not all(
            num_edge_type >= len(split_ratio)
            for split_type, num_edge_type
            in self.num_edges(split_types).items()
        ):
            raise ValueError(
                "in _split_edge num of edges of a specific type is smaller "
                "than the number of splitted parts"
            )

        split_types_all_flag = split_types == self.message_types

        if self.G is not None:
            edges = list(self.G.edges(data=True))
            random.shuffle(edges)
        else:
            edges = {}
            for message_type in self.message_types:
                edges[message_type] = (
                    torch.randperm(self.num_edges(message_type))
                )

        if edge_split_mode == "approximate" and not split_types_all_flag:
            warnings.warn(
                "in _split_edge when edge_split_mode is set to be approximate "
                "split_types does not cover all types, in this case "
                "the splitting is not going to improve much compared "
                "to when _split_edge when edge_split_mode is exact."
            )

        # Split edges by going through edges in each edge types and divide them
        # according to split_ratio.
        if edge_split_mode == "exact":
            if self.G is not None:
                edges_train, edges_val, edges_test = [], [], []
            else:
                edges_train, edges_val, edges_test = {}, {}, {}
            edges_split_type_dict = {}
            if self.G is not None:
                for edge in edges:
                    edge_type = edge[2]["edge_type"]
                    source_node_idx = edge[0]
                    target_node_idx = edge[1]
                    source_node_type = (
                        self.G.nodes[source_node_idx]["node_type"]
                    )
                    target_node_type = (
                        self.G.nodes[target_node_idx]["node_type"]
                    )
                    edge_split_type = (
                        source_node_type,
                        edge_type,
                        target_node_type,
                    )

                    if edge_split_type not in edges_split_type_dict:
                        edges_split_type_dict[edge_split_type] = []
                    edges_split_type_dict[edge_split_type].append(edge)
            else:
                edges_split_type_dict = edges

            for split_type in self.message_types:
                edges_split_type = edges_split_type_dict[split_type]
                edges_split_type_length = len(edges_split_type)
                if len(split_ratio) == 2:
                    if split_type in split_types:
                        num_edges_train = (
                            1 +
                            int(split_ratio[0] * (edges_split_type_length - 2))
                        )
                        if self.G is not None:
                            edges_train += edges_split_type[:num_edges_train]
                            edges_val += edges_split_type[num_edges_train:]
                        else:
                            edges_train[split_type] = (
                                edges_split_type[:num_edges_train]
                            )
                            edges_val[split_type] = (
                                edges_split_type[num_edges_train:]
                            )
                    else:
                        if self.G is not None:
                            edges_train += edges_split_type
                            edges_val += edges_split_type
                        else:
                            edges_train[split_type] = edges_split_type
                            edges_val[split_type] = edges_split_type

                # perform `secure split` s.t. guarantees all splitted subgraph
                # of a split type contains at least one edge.
                elif len(split_ratio) == 3:
                    if split_type in split_types:
                        num_edges_train = (
                            1 +
                            int(split_ratio[0] * (edges_split_type_length - 3))
                        )
                        num_edges_val = (
                            1 +
                            int(split_ratio[1] * (edges_split_type_length - 3))
                        )

                        if self.G is not None:
                            edges_train += edges_split_type[:num_edges_train]
                            edges_val += (
                                edges_split_type[
                                    num_edges_train:
                                    num_edges_train + num_edges_val
                                ]
                            )
                            edges_test += (
                                edges_split_type[
                                    num_edges_train + num_edges_val:
                                ]
                            )
                        else:
                            edges_train[split_type] = (
                                edges_split_type[:num_edges_train]
                            )
                            edges_val[split_type] = (
                                edges_split_type[
                                    num_edges_train:
                                    num_edges_train + num_edges_val
                                ]
                            )
                            edges_test[split_type] = (
                                edges_split_type[
                                    num_edges_train + num_edges_val:
                                ]
                            )

                    else:
                        if self.G is not None:
                            edges_train += edges_split_type
                            edges_val += edges_split_type
                            edges_test += edges_split_type
                        else:
                            edges_train[split_type] = edges_split_type
                            edges_val[split_type] = edges_split_type
                            edges_test[split_type] = edges_split_type

        elif edge_split_mode == "approximate":
            # if split_types do not cover all edge types in hetero_graph
            # then we need to do the filtering
            if not split_types_all_flag:
                if self.G is not None:
                    edges_split_type = []
                    edges_non_split_type = []
                    for edge in edges:
                        edge_type = edge[2]["edge_type"]
                        source_node_idx = edge[0]
                        target_node_idx = edge[1]
                        source_node_type = (
                            self.G.nodes[source_node_idx]["node_type"]
                        )
                        target_node_type = (
                            self.G.nodes[target_node_idx]["node_type"]
                        )
                        edge_split_type = (
                            source_node_type,
                            edge_type,
                            target_node_type
                        )
                        if edge_split_type in split_types:
                            edges_split_type.append(edge)
                        else:
                            edges_non_split_type.append(edge)

                    edges_split_type_length = len(edges_split_type)

                    # perform `secure split` s.t. guarantees all splitted subgraph
                    # of a split type contains at least one edge.
                    if len(split_ratio) == 2:
                        num_edges_train = (
                            1
                            + int(
                                split_ratio[0] * (edges_split_type_length - 2)
                            )
                        )

                        edges_train = (
                            edges_split_type[:num_edges_train]
                            + edges_non_split_type
                        )
                        edges_val = (
                            edges_split_type[num_edges_train:]
                            + edges_non_split_type
                        )
                    elif len(split_ratio) == 3:
                        num_edges_train = (
                            1
                            + int(
                                split_ratio[0] * (edges_split_type_length - 3)
                            )
                        )
                        num_edges_val = (
                            1
                            + int(
                                split_ratio[1] * (edges_split_type_length - 3)
                            )
                        )

                        edges_train = (
                            edges_split_type[:num_edges_train]
                            + edges_non_split_type
                        )
                        edges_val = (
                            edges_split_type[
                                num_edges_train:num_edges_train + num_edges_val
                            ]
                            + edges_non_split_type
                        )
                        edges_test = (
                            edges_split_type[num_edges_train + num_edges_val:]
                            + edges_non_split_type
                        )
                else:
                    split_offset = 0
                    cumulative_split_type_cnt = []
                    message_types_sorted = sorted(self.message_types)
                    split_types_sorted = [
                        message_type for message_type
                        in message_types_sorted if message_type in split_types
                    ]

                    for split_type in split_types_sorted:
                        cumulative_split_type_cnt.append(split_offset)
                        split_offset += edges[split_type].shape[0]

                    cumulative_split_type_cnt.append(split_offset)
                    edges_split_type_length = split_offset
                    edge_index = list(range(edges_split_type_length))
                    random.shuffle(edge_index)

                    if len(split_ratio) == 2:
                        num_edges_train = (
                            1 +
                            int(split_ratio[0] * (edges_split_type_length - 2))
                        )

                        edges_train_index = sorted(
                            edge_index[:num_edges_train]
                        )
                        edges_val_index = sorted(
                            edge_index[num_edges_train:]
                        )
                        edges_train, edges_val = {}, {}
                        split_type_cnt = 0
                        for index in edges_train_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_train:
                                edges_train[split_type] = []
                            edges_train[split_type].append(index_type)

                        split_type_cnt = 0
                        for index in edges_val_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_val:
                                edges_val[split_type] = []
                            edges_val[split_type].append(index_type)

                        for split_type in edges_train:
                            edges_train[split_type] = torch.tensor(
                                edges_train[split_type]
                            )
                        for split_type in edges_val:
                            edges_val[split_type] = torch.tensor(
                                edges_val[split_type]
                            )

                        for split_type in message_types_sorted:
                            if split_type not in split_types:
                                edges_train[split_type] = edges[split_type]
                                edges_val[split_type] = edges[split_type]

                    elif len(split_ratio) == 3:
                        num_edges_train = (
                            1
                            + int(
                                split_ratio[0] * (edges_split_type_length - 3)
                            )
                        )
                        num_edges_val = (
                            1
                            + int(
                                split_ratio[1] * (edges_split_type_length - 3)
                            )
                        )

                        edges_train_index = sorted(
                            edge_index[:num_edges_train]
                        )
                        edges_val_index = sorted(
                            edge_index[
                                num_edges_train:num_edges_train + num_edges_val
                            ]
                        )
                        edges_test_index = sorted(
                            edge_index[num_edges_train + num_edges_val:]
                        )
                        edges_train, edges_val, edges_test = {}, {}, {}
                        split_type_cnt = 0
                        for index in edges_train_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_train:
                                edges_train[split_type] = []
                            edges_train[split_type].append(index_type)

                        split_type_cnt = 0
                        for index in edges_val_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_val:
                                edges_val[split_type] = []
                            edges_val[split_type].append(index_type)

                        split_type_cnt = 0
                        for index in edges_test_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_test:
                                edges_test[split_type] = []
                            edges_test[split_type].append(index_type)

                        for split_type in edges_train:
                            edges_train[split_type] = torch.tensor(
                                edges_train[split_type]
                            )
                        for split_type in edges_val:
                            edges_val[split_type] = torch.tensor(
                                edges_val[split_type]
                            )
                        for split_type in edges_test:
                            edges_test[split_type] = torch.tensor(
                                edges_test[split_type]
                            )

                        for split_type in message_types_sorted:
                            if split_type not in split_types:
                                edges_train[split_type] = edges[split_type]
                                edges_val[split_type] = edges[split_type]
                                edges_test[split_type] = edges[split_type]
            else:
                # if split_types cover all edge types in hetero_graph then we
                # need not do the filtering and achieve maximal optimization
                # as compared to exact split by splitting all the edges
                # regardless of edge types

                if self.G is not None:
                    num_edges = sum(self.num_edges().values())

                    # perform `secure split` s.t. guarantees all splitted subgraph
                    # contains at least one edge.
                    if len(split_ratio) == 2:
                        num_edges_train = (
                            1 + int(split_ratio[0] * (num_edges - 2))
                        )

                        edges_train = edges[:num_edges_train]
                        edges_val = edges[num_edges_train:]
                    elif len(split_ratio) == 3:
                        num_edges_train = (
                            1 + int(split_ratio[0] * (num_edges - 3))
                        )
                        num_edges_val = (
                            1 + int(split_ratio[1] * (num_edges - 3))
                        )

                        edges_train = edges[:num_edges_train]
                        edges_val = (
                            edges[
                                num_edges_train:num_edges_train + num_edges_val
                            ]
                        )
                        edges_test = edges[num_edges_train + num_edges_val:]
                else:
                    split_offset = 0
                    cumulative_split_type_cnt = []
                    split_types_sorted = sorted(self.message_types)
                    for split_type in split_types_sorted:
                        cumulative_split_type_cnt.append(split_offset)
                        split_offset += edges[split_type].shape[0]

                    cumulative_split_type_cnt.append(split_offset)
                    edges_split_type_length = split_offset
                    edge_index = list(range(edges_split_type_length))
                    random.shuffle(edge_index)

                    if len(split_ratio) == 2:
                        num_edges_train = (
                            1
                            + int(
                                split_ratio[0] * (edges_split_type_length - 2)
                            )
                        )

                        edges_train_index = sorted(
                            edge_index[:num_edges_train]
                        )
                        edges_val_index = sorted(edge_index[num_edges_train:])
                        edges_train, edges_val = {}, {}

                        split_type_cnt = 0
                        for index in edges_train_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_train:
                                edges_train[split_type] = []
                            edges_train[split_type].append(index_type)

                        split_type_cnt = 0
                        for index in edges_val_index:
                            # if not (
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_val:
                                edges_val[split_type] = []
                            edges_val[split_type].append(index_type)

                        for split_type in edges_train:
                            edges_train[split_type] = torch.tensor(
                                edges_train[split_type]
                            )
                        for split_type in edges_val:
                            edges_val[split_type] = torch.tensor(
                                edges_val[split_type]
                            )

                    elif len(split_ratio) == 3:
                        num_edges_train = (
                            1
                            + int(
                                split_ratio[0] * (edges_split_type_length - 3)
                            )
                        )
                        num_edges_val = (
                            1
                            + int(
                                split_ratio[1] * (edges_split_type_length - 3)
                            )
                        )

                        edges_train_index = sorted(
                            edge_index[:num_edges_train]
                        )
                        edges_val_index = sorted(
                            edge_index[
                                num_edges_train:num_edges_train + num_edges_val
                            ]
                        )
                        edges_test_index = sorted(
                            edge_index[num_edges_train + num_edges_val:]
                        )
                        edges_train, edges_val, edges_test = {}, {}, {}
                        split_type_cnt = 0
                        for index in edges_train_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_train:
                                edges_train[split_type] = []
                            edges_train[split_type].append(index_type)

                        split_type_cnt = 0
                        for index in edges_val_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_val:
                                edges_val[split_type] = []
                            edges_val[split_type].append(index_type)

                        split_type_cnt = 0
                        for index in edges_test_index:
                            while not (
                                cumulative_split_type_cnt[split_type_cnt]
                                <= index
                                < cumulative_split_type_cnt[split_type_cnt+1]
                            ):
                                split_type_cnt += 1
                            split_type = split_types_sorted[split_type_cnt]
                            index_type = (
                                index
                                - cumulative_split_type_cnt[split_type_cnt]
                            )
                            if split_type not in edges_test:
                                edges_test[split_type] = []
                            edges_test[split_type].append(index_type)

                        for split_type in edges_train:
                            edges_train[split_type] = torch.tensor(
                                edges_train[split_type]
                            )
                        for split_type in edges_val:
                            edges_val[split_type] = torch.tensor(
                                edges_val[split_type]
                            )
                        for split_type in edges_test:
                            edges_test[split_type] = torch.tensor(
                                edges_test[split_type]
                            )

        if self.G is not None:
            graph_train = HeteroGraph(
                self._edge_subgraph_with_isonodes(self.G, edges_train)
            )
        else:
            graph_train = copy.copy(self)

            # update edge_index
            edge_index = {}
            for message_type in edges_train:
                edge_index[message_type] = torch.index_select(
                    self.edge_index[message_type], 1, edges_train[message_type]
                )
                if self.is_undirected():
                    edge_index[message_type] = torch.cat(
                        [
                            edge_index[message_type],
                            torch.flip(edge_index[message_type], [0])
                        ],
                        dim=1
                    )

            # update the other edge_features
            graph_train.edge_index = edge_index
            for key in graph_train.keys:
                if self._is_edge_attribute(key):
                    edge_feature = {}
                    for message_type in edges_train:
                        edge_feature[message_type] = torch.index_select(
                            self[key][message_type],
                            0,
                            edges_train[message_type]
                        )
                        if self.is_undirected():
                            edge_feature[message_type] = torch.cat(
                                [
                                    edge_feature[message_type],
                                    edge_feature[message_type]
                                ],
                                dim=0
                            )
                    graph_train[key] = edge_feature

        graph_val = copy.copy(graph_train)
        if len(split_ratio) == 3:
            if self.G is not None:
                graph_test = HeteroGraph(
                    self._edge_subgraph_with_isonodes(
                        self.G, edges_train + edges_val
                    )
                )
            else:
                graph_test = copy.copy(self)
                edge_index = {}
                for message_type in edges_test:
                    if message_type in split_types:
                        edge_index[message_type] = torch.tensor(
                            [], dtype=self.edge_index[message_type].dtype
                        )
                        if message_type in edges_train:
                            edge_index[message_type] = torch.cat(
                                [
                                    edge_index[message_type],
                                    torch.index_select(
                                        self.edge_index[message_type],
                                        1,
                                        edges_train[message_type]
                                    )
                                ],
                                dim=1
                            )
                        if message_type in edges_val:
                            edge_index[message_type] = torch.cat(
                                [
                                    edge_index[message_type],
                                    torch.index_select(
                                        self.edge_index[message_type],
                                        1,
                                        edges_val[message_type]
                                    )
                                ],
                                dim=1
                            )
                    else:
                        edge_index[message_type] = torch.index_select(
                            self.edge_index[message_type],
                            1,
                            edges_train[message_type]
                        )
                    if self.is_undirected():
                        edge_index[message_type] = torch.cat(
                            [
                                edge_index[message_type],
                                torch.flip(edge_index[message_type], [0])
                            ],
                            dim=1
                        )

                graph_test.edge_index = edge_index
                for key in graph_test.keys:
                    if self._is_edge_attribute(key):
                        for message_type in self[key]:
                            if message_type in split_types:
                                edge_feature[message_type] = torch.tensor(
                                    [], dtype=self[key][message_type].dtype
                                )
                                if message_type in edges_train:
                                    edge_feature[message_type] = torch.cat(
                                        [
                                            edge_feature[message_type],
                                            torch.index_select(
                                                self[key][message_type],
                                                0,
                                                edges_train[message_type]
                                            )
                                        ]
                                    )

                                if message_type in edges_val:
                                    edge_feature[message_type] = torch.cat(
                                        [
                                            edge_feature[message_type],
                                            torch.index_select(
                                                self[key][message_type],
                                                0,
                                                edges_val[message_type]
                                            )
                                        ]
                                    )
                            else:
                                edge_feature[message_type] = (
                                    torch.index_select(
                                        self[key][message_type],
                                        0,
                                        edges_train[message_type]
                                    )
                                )
                            if self.is_undirected():
                                edge_feature[message_type] = torch.cat(
                                    [
                                        edge_feature[message_type],
                                        edge_feature[message_type]
                                    ],
                                    dim=0
                                )
                        graph_test[key] = edge_feature

        # set objective
        if self.G is not None:
            self._create_label_link_pred(
                graph_train,
                edges_train,
                list(self.G.nodes(data=True))
            )
            self._create_label_link_pred(
                graph_val,
                edges_val,
                list(self.G.nodes(data=True))
            )
        else:
            self._create_label_link_pred(
                graph_train, edges_train
            )
            self._create_label_link_pred(
                graph_val, edges_val
            )

        if len(split_ratio) == 3:
            if self.G is not None:
                self._create_label_link_pred(
                    graph_test,
                    edges_test,
                    list(self.G.nodes(data=True))
                )
            else:
                self._create_label_link_pred(
                    graph_test, edges_test
                )
            return [graph_train, graph_val, graph_test]
        else:
            return [graph_train, graph_val]

    def split(
        self,
        task: str = "node",
        split_types: Union[str, List[str], tuple, List[tuple]] = None,
        split_ratio: List[float] = None,
        edge_split_mode: str = "exact",
    ):
        r"""
        Split current graph object to list of graph objects.

        Args:
            task (string): One of `node`, `edge` or `link_pred`.
            split_types (list): Types splitted on. Default is `None` which will split all the types in
                specified task.
            split_ratio (array_like): Array_like ratios `[train_ratio, validation_ratio, test_ratio]`.

        Returns:
            list: A Python list of Graph objects with specified task.
        """
        if split_ratio is None:
            split_ratio = [0.8, 0.1, 0.1]
        if not isinstance(split_ratio, list):
            raise TypeError("Split ratio must be a list.")
        if (len(split_ratio) != 3):
            raise ValueError("Split ratio must contain three values.")
        if not math.isclose(sum(split_ratio), 1.0):
            raise ValueError("Split ratio must sum up to 1.")
        if not all(
            isinstance(split_ratio_i, float)
            for split_ratio_i in split_ratio
        ):
            raise TypeError("Split ratio must contain all floats.")
        if not all(
            split_ratio_i > 0 for split_ratio_i in split_ratio
        ):
            raise ValueError("Split ratio must contain all positivevalues.")

        if (
            (
                task == "node"
                and (
                    isinstance(split_types, str)
                    or isinstance(split_types, int)
                    or isinstance(split_types, float)
                )
            )
            or (
                (
                    task == "edge" or task == "link_pred"
                )
                and isinstance(split_types, tuple)
                and len(split_types) == 3
                and
                (
                    all(
                        isinstance(x, str)
                        or isinstance(x, int)
                        or isinstance(x, float)
                        for x in split_types
                    )
                )
            )
        ):
            split_types = [split_types]

        if task == "node":
            return self._split_node(split_types, split_ratio)
        elif task == "edge":
            return self._split_edge(split_types, split_ratio)
        elif task == "link_pred":
            return self.split_link_pred(
                split_types,
                split_ratio,
                edge_split_mode,
            )
        elif task == "graph":
            raise ValueError("Graph task does not split individual graphs.")
        else:
            raise ValueError("Unknown task.")

    def _custom_create_neg_sampling(
        self,
        negative_sampling_ratio: float,
        split_types: List[str] = None,
        resample: bool = False
    ):
        r"""
        Args:
            negative_sampling_ratio (float or int): ratio of negative sampling edges compared with the original edges.
            resample (boolean): whether should resample.
        """
        if split_types is None:
            split_types = self.message_types
        if not isinstance(split_types, list):
            raise TypeError("Split_types must be string or list of string.")
        if not all(
            [
                split_type in self.message_types
                for split_type in split_types
            ]
        ):
            raise ValueError(
                "Split type in split_types must exist in self.node_label_index"
            )

        # filter split_types
        split_types = (
            [
                message_type for message_type in split_types
                if message_type in self.edge_label_index
            ]
        )

        if resample and self._num_positive_examples is not None:
            for (
                message_type, edge_type_positive_num
            ) in self._num_positive_examples.items():
                self.edge_label_index[message_type] = (
                    self.edge_label_index[message_type][
                        :, :edge_type_positive_num
                    ]
                )

        num_pos_edges = (
            {
                message_type: edge_type_positive.shape[-1]
                for message_type, edge_type_positive
                in self.edge_label_index.items()
            }
        )
        num_neg_edges = (
            {
                message_type: int(edge_type_num * negative_sampling_ratio)
                for message_type, edge_type_num in num_pos_edges.items()
                if message_type in split_types
            }
        )

        if (
            set(self.edge_index.keys()) == set(self.edge_label_index.keys())
            and all(
                self.edge_index[message_type].size(1)
                == self.edge_label_index[message_type].size(1)
                for message_type in split_types
            )
            and all(
                torch.sum(
                    self.edge_index[message_type]
                    - self.edge_label_index[message_type]
                ) == 0
                for message_type in split_types
            )
        ):
            edge_index_all = (
                {
                    message_type: edge_type_positive
                    for message_type, edge_type_positive
                    in self.edge_index.items()
                    if message_type in split_types
                }
            )
        else:
            edge_index_all = {}
            for message_type in split_types:
                edge_index_all[message_type] = (
                    torch.cat(
                        (
                            self.edge_index[message_type],
                            self.edge_label_index[message_type]
                        ),
                        -1,
                    )
                )

        if not isinstance(self.negative_edge, dict):
            negative_edge_dict = {}
            for edge in self.negative_edge:
                head_type = self.G.nodes[edge[0]]["node_type"]
                tail_type = self.G.nodes[edge[1]]["node_type"]
                edge_type = edge[-1]["edge_type"]
                message_type = (head_type, edge_type, tail_type)
                if message_type not in negative_edge_dict:
                    negative_edge_dict[message_type] = []
                negative_edge_dict[message_type].append(edge[:-1])

            # sanity check
            negative_message_types = [x for x in negative_edge_dict]
            for split_type in self.message_types:
                if (
                    (split_type in split_types)
                    and (split_type not in negative_message_types)
                ):
                    raise ValueError(
                        "negative edges don't contain "
                        "message_type: {split_type} which is in split_types."
                    )
                elif (
                    (split_type not in split_types)
                    and (split_type in negative_message_types)
                ):
                    raise ValueError(
                        "negative edges contain message_type: "
                        "{split_type} which is not in split_types."
                    )

            for message_type in negative_edge_dict:
                negative_edge_message_type_length = (
                    len(negative_edge_dict[message_type])
                )
                num_neg_edges_message_type_length = num_neg_edges[message_type]
                if (
                    negative_edge_message_type_length
                    < num_neg_edges_message_type_length
                ):
                    multiplicity = math.ceil(
                        num_neg_edges_message_type_length
                        / negative_edge_message_type_length
                    )
                    negative_edge_dict[message_type] = (
                        negative_edge_dict[message_type]
                        * multiplicity
                    )
                    negative_edge_dict[message_type] = (
                        negative_edge_dict[message_type][
                            :num_neg_edges_message_type_length
                        ]
                    )

            # re-initialize self.negative_edge
            # initialize self.negative_edge_index
            self.negative_edge_idx = {
                message_type: 0
                for message_type in negative_edge_dict
            }

            negative_edge = {}
            for message_type in negative_edge_dict:
                negative_edge[message_type] = (
                    torch.tensor(list(zip(*negative_edge_dict[message_type])))
                )
            self.negative_edge = negative_edge

        negative_edges = self.negative_edge
        for message_type in negative_edges:
            negative_edge_message_type_length = (
                negative_edges[message_type].shape[1]
            )
            negative_edge_idx_message_type = (
                self.negative_edge_idx[message_type]
            )
            num_neg_edges_message_type_length = (
                num_neg_edges[message_type]
            )

            if (
                negative_edge_idx_message_type
                + num_neg_edges_message_type_length
                > negative_edge_message_type_length
            ):
                negative_edges_message_type_begin = (
                    negative_edges[message_type][
                        :, negative_edge_idx_message_type:
                    ]
                )

                negative_edges_message_type_end = (
                    negative_edges[message_type][
                        :, :negative_edge_idx_message_type
                        + num_neg_edges_message_type_length
                        - negative_edge_message_type_length
                    ]
                )

                negative_edges[message_type] = torch.cat(
                    [
                        negative_edges_message_type_begin,
                        negative_edges_message_type_end
                    ], axis=1
                )
            else:
                negative_edges[message_type] = (
                    negative_edges[message_type][
                        :, negative_edge_idx_message_type:
                        negative_edge_idx_message_type
                        + num_neg_edges_message_type_length
                    ]
                )

            self.negative_edge_idx[message_type] = (
                (
                    negative_edge_idx_message_type
                    + num_neg_edges_message_type_length
                )
                % negative_edge_message_type_length
            )

        if not resample:
            if self.edge_label is None:
                positive_label = (
                    {
                        message_type: torch.ones(
                            edge_type_positive,
                            dtype=torch.long
                        )
                        for message_type, edge_type_positive
                        in num_pos_edges.items()
                    }
                )

                negative_label = (
                    {
                        message_type: torch.zeros(
                            edge_type_negative,
                            dtype=torch.long
                        )
                        for message_type, edge_type_negative
                        in num_neg_edges.items()
                    }
                )
            else:
                positive_label = (
                    {
                        message_type: edge_type_positive
                        for message_type, edge_type_positive
                        in self.edge_label.items()
                        if message_type in split_types
                    }
                )

                negative_label = (
                    {
                        message_type:
                        (torch.max(positive_label[message_type]) + 1)
                        * torch.ones(
                            edge_type_negative,
                            dtype=torch.long
                        )
                        for message_type, edge_type_negative
                        in num_neg_edges.items()
                    }
                )

            self.edge_label = (
                {
                    message_type:
                    torch.cat(
                        (
                            positive_label[message_type],
                            negative_label[message_type]
                        ),
                        -1,
                    ).type(torch.long)
                    for message_type in split_types
                }
            )

        self._num_positive_examples = num_pos_edges

        for message_type in split_types:
            self.edge_label_index[message_type] = (
                torch.cat(
                    (
                        self.edge_label_index[message_type],
                        negative_edges[message_type]
                    ),
                    -1,
                )
            )

    def _create_neg_sampling(
        self,
        negative_sampling_ratio: float,
        split_types: List[str] = None,
        resample: bool = False
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
        if split_types is None:
            split_types = self.message_types
        if not isinstance(split_types, list):
            raise TypeError("Split_types must be string or list of string.")
        if not all(
            [
                split_type in self.message_types
                for split_type in split_types
            ]
        ):
            raise ValueError(
                "Split type in split_types must exist in self.node_label_index"
            )

        # filter split_types
        split_types = (
            [
                message_type for message_type in split_types
                if message_type in self.edge_label_index
            ]
        )

        if resample and self._num_positive_examples is not None:
            for (
                message_type, edge_type_positive_num
            ) in self._num_positive_examples.items():
                self.edge_label_index[message_type] = (
                    self.edge_label_index[message_type][
                        :, :edge_type_positive_num
                    ]
                )

        num_pos_edges = (
            {
                message_type: edge_type_positive.shape[-1]
                for message_type, edge_type_positive
                in self.edge_label_index.items()
                if message_type in split_types
            }
        )
        num_neg_edges = (
            {
                message_type: int(edge_type_num * negative_sampling_ratio)
                for message_type, edge_type_num
                in num_pos_edges.items()
            }
        )

        if (
            set(self.edge_index.keys()) == set(self.edge_label_index.keys())
            and all(
                self.edge_index[message_type].size(1)
                == self.edge_label_index[message_type].size(1)
                for message_type in split_types
            )
            and all(
                torch.sum(
                    self.edge_index[message_type]
                    - self.edge_label_index[message_type]
                ) == 0
                for message_type in split_types
            )
        ):
            edge_index_all = (
                {
                    message_type: edge_type_positive
                    for message_type, edge_type_positive
                    in self.edge_index.items()
                    if message_type in split_types
                }
            )
        else:
            edge_index_all = {}
            for message_type in split_types:
                edge_index_all[message_type] = (
                    torch.cat(
                        (
                            self.edge_index[message_type],
                            self.edge_label_index[message_type]
                        ),
                        -1,
                    )
                )

        negative_edges = (
            self.negative_sampling(
                edge_index_all,
                self.num_nodes(),
                num_neg_edges,
            )
        )

        if not resample:
            if self.edge_label is None:
                positive_label = (
                    {
                        message_type: torch.ones(
                            edge_type_positive,
                            dtype=torch.long
                        )
                        for message_type, edge_type_positive
                        in num_pos_edges.items()
                    }
                )

                negative_label = (
                    {
                        message_type: torch.zeros(
                            edge_type_negative,
                            dtype=torch.long
                        )
                        for message_type, edge_type_negative
                        in num_neg_edges.items()
                    }
                )
            else:
                positive_label = (
                    {
                        message_type: edge_type_positive
                        for message_type, edge_type_positive
                        in self.edge_label.items()
                    }
                )

                negative_label = (
                    {
                        message_type:
                        (torch.max(positive_label[message_type]) + 1)
                        * torch.ones(
                            edge_type_negative,
                            dtype=torch.long
                        )
                        for message_type, edge_type_negative
                        in num_neg_edges.items()
                    }
                )

            self.edge_label = (
                {
                    message_type:
                    torch.cat(
                        (
                            positive_label[message_type],
                            negative_label[message_type]
                        ),
                        -1,
                    ).type(torch.long)
                    for message_type in split_types
                }
            )

        self._num_positive_examples = num_pos_edges

        for message_type in split_types:
            self.edge_label_index[message_type] = (
                torch.cat(
                    (
                        self.edge_label_index[message_type],
                        negative_edges[message_type]
                    ),
                    -1,
                )
            )

    @staticmethod
    def negative_sampling(
        edge_index: Dict[str, torch.tensor],
        num_nodes=None,
        num_neg_samples: Dict[str, int] = None,
    ):
        r"""Samples random negative edges of a heterogeneous graph given by :attr:`edge_index`.

        Args:
            edge_index (LongTensor): The edge indices.
            num_nodes (int, optional): The number of nodes, *i.e.*
                :obj:`max_val + 1` of :attr:`edge_index`. (default: :obj:`None`)
            num_neg_samples (int, optional): The number of negative samples to
                return. If set to :obj:`None`, will try to return a negative edge
                for every positive edge. (default: :obj:`None`)
            force_undirected (bool, optional): If set to :obj:`True`, sampled
                negative edges will be undirected. (default: :obj:`False`)

        :rtype: :class:`torch.LongTensor`
        """

        num_neg_samples = (
            {
                message_type:
                min(
                    num_neg_samples[message_type],
                    num_nodes[message_type[0]]
                    * num_nodes[message_type[2]]
                    - edge_index[message_type].size(1)
                )
                for message_type in edge_index
            }
        )

        rng = {}
        for message_type in edge_index:
            head_type = message_type[0]
            tail_type = message_type[2]
            rng[message_type] = range(
                num_nodes[head_type] * num_nodes[tail_type]
            )

        idx = {}
        for message_type in edge_index:
            head_type = message_type[0]
            tail_type = message_type[2]
            if num_nodes[head_type] >= num_nodes[tail_type]:
                idx[message_type] = (
                    edge_index[message_type][0]
                    * num_nodes[tail_type]
                    + edge_index[message_type][1]
                )
            else:
                idx[message_type] = (
                    edge_index[message_type][1]
                    * num_nodes[head_type]
                    + edge_index[message_type][0]
                )

        perm = {}
        for message_type in edge_index:
            samples = random.sample(
                rng[message_type],
                num_neg_samples[message_type]
            )
            perm[message_type] = torch.tensor(samples)

        mask = (
            {
                message_type: torch.from_numpy(
                    np.isin(
                        perm[message_type],
                        idx[message_type]
                    )
                ).to(torch.bool)
                for message_type in edge_index
            }
        )
        rest = (
            {
                message_type: torch.nonzero(mask[message_type]).view(-1)
                for message_type in edge_index
            }
        )

        for message_type in edge_index:
            while rest[message_type].numel() > 0:
                tmp = torch.tensor(
                    random.sample(
                        rng[message_type],
                        rest[message_type].size(0)
                    )
                )
                mask = (
                    torch.from_numpy(
                        np.isin(tmp, idx[message_type])
                    ).to(torch.bool)
                )
                perm[message_type][rest[message_type]] = tmp
                rest[message_type] = (
                    rest[message_type][torch.nonzero(mask).view(-1)]
                )

        row, col = {}, {}
        for message_type in perm:
            head_type = message_type[0]
            tail_type = message_type[2]

            if num_nodes[head_type] >= num_nodes[tail_type]:
                row[message_type] = perm[message_type] // num_nodes[tail_type]
                col[message_type] = perm[message_type] % num_nodes[tail_type]
            else:
                row[message_type] = perm[message_type] % num_nodes[head_type]
                col[message_type] = perm[message_type] // num_nodes[head_type]

        neg_edge_index = (
            {
                message_type: torch.stack(
                    [
                        row[message_type],
                        col[message_type]
                    ],
                    dim=0,
                ).long()
                for message_type in edge_index
            }
        )

        for message_type in edge_index:
            neg_edge_index[message_type].to(
                neg_edge_index[message_type].device
            )
        return neg_edge_index

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
        if (
            isinstance(key, tuple)
            and torch.is_tensor(value)
            and len(value.shape) == 2
            and value.shape[0] == 2
            and value.shape[1] >= self.num_edges(key)
        ):
            return -1
        return 0

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
        if (
            isinstance(key, tuple)
            and torch.is_tensor(value)
            and len(value.shape) == 2
            and value.shape[0] == 2
            and value.shape[1] >= self.num_edges(key)
        ):
            node_type_start, _, node_type_end = key
            return torch.tensor(
                [
                    [self.num_nodes(node_type_start)],
                    [self.num_nodes(node_type_end)],
                ]
            )
        return 0
