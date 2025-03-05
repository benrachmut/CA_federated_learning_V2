
import torchvision
from torch.utils.data import DataLoader, Dataset
from config import *
import torch.nn.functional as F
from itertools import combinations
from sklearn.cluster import KMeans

from abc import ABC, abstractmethod

# Define AlexNet for clients

import numpy as np

import torch
import torch.nn as nn



class AlexNet(nn.Module):
    def __init__(self, num_classes, num_clusters=1):
        super(AlexNet, self).__init__()

        # Backbone (shared layers)
        self.backbone = nn.Sequential(
            nn.Conv2d(3, 64, kernel_size=3, stride=1, padding=1), nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),

            nn.Conv2d(64, 128, kernel_size=3, stride=1, padding=1), nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),

            nn.Conv2d(128, 256, kernel_size=3, stride=1, padding=1), nn.ReLU(),
            nn.Conv2d(256, 256, kernel_size=3, stride=1, padding=1), nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),

            nn.Conv2d(256, 512, kernel_size=3, stride=1, padding=1), nn.ReLU(),
            nn.Conv2d(512, 512, kernel_size=3, stride=1, padding=1), nn.ReLU(),
            nn.MaxPool2d(kernel_size=2, stride=2),

            nn.Flatten(),
            nn.Linear(512 * 2 * 2, 4096), nn.ReLU(),
            nn.Dropout(),
            nn.Linear(4096, 4096), nn.ReLU(),
            nn.Dropout()
        )

        # If there's only 1 head, keep it simple (like original)
        if num_clusters == 1:
            self.head = nn.Linear(4096, num_classes)  # Single head
        else:
            # Multi-head with deeper structures
            self.heads = nn.ModuleDict({
                f"head_{i}": nn.Sequential(
                    nn.Linear(4096, 2048), nn.ReLU(),
                    nn.Linear(2048, 1024), nn.ReLU(),
                    nn.Linear(1024, num_classes)
                ) for i in range(num_clusters)
            })

        self.num_clusters = num_clusters

    def forward(self, x, cluster_id=None):
        x = self.backbone(x)

        if self.num_clusters == 1:
            return self.head(x)  # Single-head case

        if cluster_id is not None:
            return self.heads[f"head_{cluster_id}"](x)  # Select head by cluster_id

        # If no cluster_id is given, return outputs from all heads
        return {f"head_{i}": head(x) for i, head in self.heads.items()}

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# Define VGG16 for server

class VGGServer(nn.Module):
    def __init__(self, num_classes, num_clusters=1):
        super(VGGServer, self).__init__()
        self.vgg = torchvision.models.vgg16(weights=None)  # No pre-trained weights
        self.vgg.classifier[6] = nn.Linear(4096, num_classes)  # Adjust for final output

        self.num_clusters = num_clusters

        if num_clusters == 1:
            # Single head case
            self.head = nn.Linear(num_classes, num_classes)
        else:
            # Multi-head with deeper layers
            self.heads = nn.ModuleDict({
                f"head_{i}": nn.Sequential(
                    nn.Linear(num_classes, 512), nn.ReLU(),
                    nn.Linear(512, 256), nn.ReLU(),
                    nn.Linear(256, num_classes)
                ) for i in range(num_clusters)
            })

    def forward(self, x, cluster_id=None):
        # Resize input to match VGG's expected input size
        x = nn.functional.interpolate(x, size=(224, 224), mode='bilinear', align_corners=False)
        x = self.vgg(x)  # Backbone output

        if self.num_clusters == 1:
            return self.head(x)  # Single-head case

        if cluster_id is not None:
            return self.heads[f"head_{cluster_id}"](x)  # Select head by cluster_id

        # If no cluster_id is given, return outputs from all heads
        return {f"head_{i}": head(x) for i, head in self.heads.items()}


def get_client_model():
    if experiment_config.client_net_type == NetType.ALEXNET:
        return AlexNet(num_classes=experiment_config.num_classes).to(device)
    if experiment_config.client_net_type == NetType.VGG:
        return VGGServer(num_classes=experiment_config.num_classes).to(device)


def get_server_model():
    if experiment_config.net_cluster_technique== NetClusterTechnique.multi_head:
        num_heads = experiment_config.num_clusters
        if isinstance(num_heads, str):
            num_heads = experiment_config.number_of_optimal_clusters
    else:
        num_heads = 1

    if experiment_config.server_net_type == NetType.ALEXNET:
        return AlexNet(num_classes=experiment_config.num_classes,num_clusters=num_heads).to(device)
    if experiment_config.server_net_type == NetType.VGG:
        return VGGServer(num_classes=experiment_config.num_classes,num_clusters=num_heads).to(device)




class LearningEntity(ABC):
    def __init__(self,id_,global_data,test_global_data):
        self.test_global_data= test_global_data

        self.global_data = global_data
        self.pseudo_label_received = {}
        self.pseudo_label_to_send = None
        self.current_iteration = 0
        self.epoch_count = 0
        self.id_ = id_
        self.model=None
        #self.weights = None
        self.accuracy_per_client_1 = {}
        #self.accuracy_per_client_5 = {}

        #self.accuracy_pl_measures= {}
        #self.accuracy_test_measures_k_half_cluster = {}
        #self.accuracy_pl_measures_k_half_cluster= {}


    def initialize_weights(self, layer):
        """Initialize weights for the model layers."""
        if isinstance(layer, (nn.Linear, nn.Conv2d)):
            nn.init.kaiming_normal_(layer.weight, mode='fan_out', nonlinearity='relu')
            if layer.bias is not None:
                nn.init.zeros_(layer.bias)

    #def set_weights(self):
        #if self.weights  is None:
        #    self.model.apply(self.initialize_weights)
        #else:
        #    self.model.apply(self.weights)

    def iterate(self,t):
        #self.set_weights()
        torch.manual_seed(self.num+t*17)
        torch.cuda.manual_seed(self.num+t*17)

        self.iteration_context(t)



        #if isinstance(self,Client):
        #    self.loss_measures[t]=self.evaluate_test_loss()
        #    self.accuracy_test_measures[t]=self.evaluate_accuracy(self.test_set)
        #    self.accuracy_pl_measures[t]=self.evaluate_accuracy(self.global_data)
        #    self.accuracy_test_measures_k_half_cluster[t]=self.evaluate_accuracy(self.test_set,self.model)
        #    self.accuracy_pl_measures_k_half_cluster[t]=self.evaluate_accuracy(self.global_data,self.model)



        #if isinstance(self,Server) and experiment_config.server_feedback_technique == ServerFeedbackTechnique.similar_to_cluster:
            #raise Exception("need to evaluate use backbone")
        #    for cluster_id in range(experiment_config.num_clusters):
        #        self.loss_measures[cluster_id][t] = self.evaluate_test_loss(cluster_id=cluster_id, model=None)
        #        self.accuracy_test_measures[cluster_id][t] = self.evaluate_accuracy(self.test_set,model= None,k=1,cluster_id=cluster_id )
        #        self.accuracy_pl_measures[cluster_id][t] = self.evaluate_accuracy(self.global_data,model= None,k=1,cluster_id=cluster_id )
        #        self.accuracy_test_measures_k_half_cluster[cluster_id][t] = self.evaluate_accuracy(self.test_set ,model= None, k = experiment_config.num_clusters // 2,cluster_id=cluster_id )
        #        self.accuracy_pl_measures_k_half_cluster[cluster_id][t] = self.evaluate_accuracy(self.global_data,model= None, k =experiment_config.num_clusters // 2,cluster_id=cluster_id )
    @abstractmethod
    def iteration_context(self,t):
        pass

    def evaluate(self, model=None):
        if model is None:
            model = self.model
    #    print("*** Generating Pseudo-Labels with Probabilities ***")

        # Create a DataLoader for the global data
        global_data_loader = DataLoader(self.global_data, batch_size=experiment_config.batch_size, shuffle=False)

        model.eval()  # Set the model to evaluation mode

        all_probs = []  # List to store the softmax probabilities
        with torch.no_grad():  # Disable gradient computation
            for inputs, _ in global_data_loader:
                inputs = inputs.to(device)
                outputs = model(inputs)  # Forward pass

                # Apply softmax to get the class probabilities
                probs = F.softmax(outputs, dim=1)  # Apply softmax along the class dimension

                all_probs.append(probs.cpu())  # Store the probabilities on CPU

        # Concatenate all probabilities into a single tensor (2D matrix)
        all_probs = torch.cat(all_probs, dim=0)

       #print(f"Shape of the 2D pseudo-label matrix: {all_probs.shape}")
        return all_probs

    def evaluate_accuracy(self, data_, model=None, k=1, cluster_id=None):
        if model is None:
            model = self.model

        """
        Evaluate the accuracy of the model on the given dataset, supporting multi-head models.

        Args:
            data_ (torch.utils.data.Dataset): The dataset to evaluate.
            model (torch.nn.Module): The model to evaluate.
            k (int): Top-k accuracy. Defaults to 1.
            cluster_id (int or None): The cluster ID for the multi-head model. If None, 
                                      the method will work as a single-head model or raise an error
                                      if multiple heads exist without specifying `cluster_id`.

        Returns:
            float: The accuracy of the model on the given dataset.
        """
        model.eval()  # Set the model to evaluation mode
        correct = 0  # To count the correct predictions
        total = 0  # To count the total predictions

        test_loader = DataLoader(data_, batch_size=experiment_config.batch_size, shuffle=False)

        with torch.no_grad():  # No need to track gradients during evaluation
            for inputs, targets in test_loader:
                inputs, targets = inputs.to(device), targets.to(device)

                # Forward pass through the specific cluster head
                outputs = model(inputs, cluster_id=cluster_id)

                # Get the top-1 predictions directly
                top_1_preds = outputs.argmax(dim=1)

                # Update the total number of predictions and correct predictions
                total += targets.size(0)
                correct += (top_1_preds == targets).sum().item()

        # Calculate accuracy as a percentage
        accuracy = 100 * correct / total if total > 0 else 0.0
        print(f"Accuracy for cluster {cluster_id if cluster_id is not None else 'default'}: {accuracy:.2f}%")
        return accuracy

    def evaluate_test_loss(self, cluster_id=None, model=None):
        """
        Evaluate the model on the test set and return the loss for a specific cluster head.

        Args:
            cluster_id (int, optional): The cluster head to use. Defaults to None, which evaluates the single head.
            model (nn.Module, optional): The model to evaluate. Defaults to `self.model`.

        Returns:
            float: The average test loss for the specified cluster head.
        """
        if model is None:
            model = self.model

        model.eval()  # Set the model to evaluation mode
        test_loader = DataLoader(self.test_set, batch_size=experiment_config.batch_size, shuffle=True)
        criterion = nn.CrossEntropyLoss()  # Define the loss function

        total_loss = 0.0
        total_samples = 0

        with torch.no_grad():  # Disable gradient computation
            for inputs, targets in test_loader:
                inputs, targets = inputs.to(device), targets.to(device)  # Move inputs and targets to device

                # Get the model outputs for the specified cluster head
                outputs = model(inputs, cluster_id=cluster_id)

                # Calculate the loss
                loss = criterion(outputs, targets)

                # Accumulate the loss
                total_loss += loss.item() * inputs.size(0)  # Multiply by the batch size
                total_samples += inputs.size(0)  # Count the number of samples

        # Calculate the average test loss
        avg_loss = total_loss / total_samples if total_samples > 0 else float('inf')
        print(f"Iteration [{self.current_iteration}], Test Loss (Cluster {cluster_id}): {avg_loss:.4f}")

        return avg_loss  # Return the average loss


class Client(LearningEntity):
    def __init__(self, id_, client_data, global_data,global_test_data,local_test_data):
        LearningEntity.__init__(self,id_,global_data,global_test_data)
        self.num = (self.id_+1)*17
        self.local_test_set= local_test_data

        self.local_data = client_data
        self.epoch_count = 0
        self.model = get_client_model()
        self.model.apply(self.initialize_weights)
        #self.train_learning_rate = experiment_config.learning_rate_train_c
        #self.weights = None
        self.global_data =global_data
        self.server = None

    def iteration_context(self, t):
        self.current_iteration = t
        #for _ in range(100):
        if t>0:
            train_loss = self.train(self.pseudo_label_received)
        train_loss = self.fine_tune()
        self.pseudo_label_to_send = self.evaluate()
        acc = self.evaluate_accuracy(self.local_test_set)

        acc_test = self.evaluate_accuracy(self.test_global_data)
            #if experiment_config.data_set_selected == DataSet.CIFAR100:
            #    if acc_test != 1:
            #        break
            #    else:
            #        self.model.apply(self.initialize_weights)
            #if experiment_config.data_set_selected == DataSet.CIFAR10:
            #    if acc_test != 10:
            #        break
            #    else:
            #        self.model.apply(self.initialize_weights)


        self.accuracy_per_client_1[t] = self.evaluate_accuracy(self.local_test_set, k=1)


    def train__(self, mean_pseudo_labels, data_):

        print(f"*** {self.__str__()} train ***")
        server_loader = DataLoader(data_, batch_size=experiment_config.batch_size, shuffle=False, num_workers=0,
                                   drop_last=True)

        self.model.train()
        criterion = nn.KLDivLoss(reduction='batchmean')
        optimizer = torch.optim.Adam(self.model.parameters(), lr=experiment_config.learning_rate_train_c)

        pseudo_targets_all = mean_pseudo_labels.to(device)

        for epoch in range(experiment_config.epochs_num_train_client):
            self.epoch_count += 1
            epoch_loss = 0

            for batch_idx, (inputs, _) in enumerate(server_loader):
                inputs = inputs.to(device)
                optimizer.zero_grad()

                outputs = self.model(inputs)
                # Check for NaN or Inf in outputs

                # Convert model outputs to log probabilities
                outputs_prob = F.log_softmax(outputs, dim=1)
                # Slice pseudo_targets to match the input batch size
                start_idx = batch_idx * experiment_config.batch_size
                end_idx = start_idx + inputs.size(0)
                pseudo_targets = pseudo_targets_all[start_idx:end_idx].to(device)

                # Check if pseudo_targets size matches the input batch size
                if pseudo_targets.size(0) != inputs.size(0):
                    print(
                        f"Skipping batch {batch_idx}: Expected pseudo target size {inputs.size(0)}, got {pseudo_targets.size(0)}")
                    continue  # Skip the rest of the loop for this batch

                # Check for NaN or Inf in pseudo targets
                if torch.isnan(pseudo_targets).any() or torch.isinf(pseudo_targets).any():
                    print(f"NaN or Inf found in pseudo targets at batch {batch_idx}: {pseudo_targets}")
                    continue

                # Normalize pseudo targets to sum to 1
                pseudo_targets = F.softmax(pseudo_targets, dim=1)

                # Calculate the loss
                loss = criterion(outputs_prob, pseudo_targets)

                # Check if the loss is NaN or Inf
                if torch.isnan(loss) or torch.isinf(loss):
                    print(f"NaN or Inf loss encountered at batch {batch_idx}: {loss}")
                    continue

                loss.backward()

                # Clip gradients
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)

                optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(server_loader)
            print(f"Epoch [{epoch + 1}/{experiment_config.epochs_num_train_client}], Loss: {avg_loss:.4f}")

        self.weights = self.model.state_dict()
        return avg_loss

    def train(self,mean_pseudo_labels):

        print(f"Mean pseudo-labels shape: {mean_pseudo_labels.shape}")  # Should be (num_data_points, num_classes)

        print(f"*** {self.__str__()} train ***")
        server_loader = DataLoader(self.global_data, batch_size=experiment_config.batch_size, shuffle=False, num_workers=0,
                                   drop_last=True)
        #server_loader = DataLoader(self.global_data, batch_size=experiment_config.batch_size, shuffle=False,
        #                           num_workers=0)
        #print(1)
        self.model.train()
        criterion = nn.KLDivLoss(reduction='batchmean')
        optimizer = torch.optim.Adam( self.model.parameters(), lr=experiment_config.learning_rate_train_c)
        #optimizer = torch.optim.Adam(self.model.parameters(), lr=experiment_config.learning_rate_train_c,
        #                             weight_decay=1e-4)

        pseudo_targets_all = mean_pseudo_labels.to(device)

        for epoch in range(experiment_config.epochs_num_train_client):
            #print(2)

            self.epoch_count += 1
            epoch_loss = 0

            for batch_idx, (inputs, _) in enumerate(server_loader):
                #print(batch_idx)

                inputs = inputs.to(device)
                optimizer.zero_grad()

                outputs =  self.model(inputs)
                # Check for NaN or Inf in outputs

                # Convert model outputs to log probabilities
                outputs_prob = F.log_softmax(outputs, dim=1)
                # Slice pseudo_targets to match the input batch size
                start_idx = batch_idx * experiment_config.batch_size
                end_idx = start_idx + inputs.size(0)
                pseudo_targets = pseudo_targets_all[start_idx:end_idx].to(device)

                # Check if pseudo_targets size matches the input batch size
                if pseudo_targets.size(0) != inputs.size(0):
                    print(
                        f"Skipping batch {batch_idx}: Expected pseudo target size {inputs.size(0)}, got {pseudo_targets.size(0)}")
                    continue  # Skip the rest of the loop for this batch

                # Check for NaN or Inf in pseudo targets
                if torch.isnan(pseudo_targets).any() or torch.isinf(pseudo_targets).any():
                    print(f"NaN or Inf found in pseudo targets at batch {batch_idx}: {pseudo_targets}")
                    continue

                # Normalize pseudo targets to sum to 1
                pseudo_targets = F.softmax(pseudo_targets, dim=1)

                # Calculate the loss
                loss = criterion(outputs_prob, pseudo_targets)

                # Check if the loss is NaN or Inf
                if torch.isnan(loss) or torch.isinf(loss):
                    print(f"NaN or Inf loss encountered at batch {batch_idx}: {loss}")
                    continue

                loss.backward()

                # Clip gradients
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)

                optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(server_loader)
            print(f"Epoch [{epoch + 1}/{experiment_config.epochs_num_train_client}], Loss: {avg_loss:.4f}")

        #self.weights =self.model.state_dict()
        return avg_loss


    def __str__(self):
        return "Client " + str(self.id_)

    def fine_tune(self):
        print("*** " + self.__str__() + " fine-tune ***")

        # Load the weights into the model
        #if self.weights is  None:
        #    self.model.apply(self.initialize_weights)
        #else:
        #    self.model.load_state_dict(self.weights)

        # Create a DataLoader for the local data
        fine_tune_loader = DataLoader(self.local_data, batch_size=experiment_config.batch_size, shuffle=True)
        self.model.train()  # Set the model to training mode

        # Define loss function and optimizer

        criterion = nn.CrossEntropyLoss()

        optimizer = torch.optim.Adam(self.model.parameters(), lr=experiment_config.learning_rate_fine_tune_c)

        epochs = experiment_config.epochs_num_input_fine_tune_clients
        for epoch in range(epochs):
            self.epoch_count += 1
            epoch_loss = 0
            for inputs, targets in fine_tune_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                optimizer.zero_grad()
                outputs = self.model(inputs)

                loss = criterion(outputs, targets)

                # Backward pass and optimization
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()

            result_to_print = epoch_loss / len(fine_tune_loader)
            print(f"Epoch [{epoch + 1}/{epochs}], Loss: {result_to_print:.4f}")
        #self.weights = self.model.state_dict()self.weights = self.model.state_dict()

        return  result_to_print

class Client_NoFederatedLearning(Client):
    def __init__(self,id_, client_data, global_data,global_test_data,local_test_data,evaluate_every):
        Client.__init__(self,id_, client_data, global_data,global_test_data,local_test_data)
        self.evaluate_every = evaluate_every

    def fine_tune(self):
        print("*** " + self.__str__() + " fine-tune ***")

        fine_tune_loader = DataLoader(self.local_data, batch_size=experiment_config.batch_size, shuffle=True)
        self.model.train()  # Set the model to training mode

        # Define loss function and optimizer

        criterion = nn.CrossEntropyLoss()

        optimizer = torch.optim.Adam(self.model.parameters(), lr=experiment_config.learning_rate_fine_tune_c)

        epochs = experiment_config.epochs_num_input_fine_tune_clients_no_fl
        for epoch in range(epochs):
            self.epoch_count += 1
            epoch_loss = 0
            for inputs, targets in fine_tune_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                optimizer.zero_grad()
                outputs = self.model(inputs)

                loss = criterion(outputs, targets)

                # Backward pass and optimization
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
            if   epoch % self.evaluate_every == 0 and epoch!=0:
                self.accuracy_per_client_1[epoch] = self.evaluate_accuracy(self.local_test_set, k=1)

            result_to_print = epoch_loss / len(fine_tune_loader)
            print(f"Epoch [{epoch + 1}/{epochs}], Loss: {result_to_print:.4f}")
        #self.weights = self.model.state_dict()self.weights = self.model.state_dict()

        return  result_to_print

class Client_PseudoLabelsClusters_with_division(Client):
    def __init__(self, id_, client_data, global_data, global_test_data, local_test_data):
        Client.__init__(self,id_, client_data, global_data,global_test_data,local_test_data)



    def train(self,mean_pseudo_labels):

        print(f"Mean pseudo-labels shape: {mean_pseudo_labels.shape}")  # Should be (num_data_points, num_classes)

        print(f"*** {self.__str__()} train ***")
        server_loader = DataLoader(self.global_data[self.current_iteration-1], batch_size=experiment_config.batch_size, shuffle=False, num_workers=0,
                                   drop_last=True)
        #server_loader = DataLoader(self.global_data, batch_size=experiment_config.batch_size, shuffle=False,
        #                           num_workers=0)
        #print(1)
        self.model.train()
        criterion = nn.KLDivLoss(reduction='batchmean')
        optimizer = torch.optim.Adam( self.model.parameters(), lr=experiment_config.learning_rate_train_c)
        #optimizer = torch.optim.Adam(self.model.parameters(), lr=experiment_config.learning_rate_train_c,
        #                             weight_decay=1e-4)

        pseudo_targets_all = mean_pseudo_labels.to(device)

        for epoch in range(experiment_config.epochs_num_train_client):
            #print(2)

            self.epoch_count += 1
            epoch_loss = 0

            for batch_idx, (inputs, _) in enumerate(server_loader):
                #print(batch_idx)

                inputs = inputs.to(device)
                optimizer.zero_grad()

                outputs =  self.model(inputs)
                # Check for NaN or Inf in outputs

                # Convert model outputs to log probabilities
                outputs_prob = F.log_softmax(outputs, dim=1)
                # Slice pseudo_targets to match the input batch size
                start_idx = batch_idx * experiment_config.batch_size
                end_idx = start_idx + inputs.size(0)
                pseudo_targets = pseudo_targets_all[start_idx:end_idx].to(device)

                # Check if pseudo_targets size matches the input batch size
                if pseudo_targets.size(0) != inputs.size(0):
                    print(
                        f"Skipping batch {batch_idx}: Expected pseudo target size {inputs.size(0)}, got {pseudo_targets.size(0)}")
                    continue  # Skip the rest of the loop for this batch

                # Check for NaN or Inf in pseudo targets
                if torch.isnan(pseudo_targets).any() or torch.isinf(pseudo_targets).any():
                    print(f"NaN or Inf found in pseudo targets at batch {batch_idx}: {pseudo_targets}")
                    continue

                # Normalize pseudo targets to sum to 1
                pseudo_targets = F.softmax(pseudo_targets, dim=1)

                # Calculate the loss
                loss = criterion(outputs_prob, pseudo_targets)

                # Check if the loss is NaN or Inf
                if torch.isnan(loss) or torch.isinf(loss):
                    print(f"NaN or Inf loss encountered at batch {batch_idx}: {loss}")
                    continue

                loss.backward()

                # Clip gradients
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)

                optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(server_loader)
            print(f"Epoch [{epoch + 1}/{experiment_config.epochs_num_train_client}], Loss: {avg_loss:.4f}")

        #self.weights =self.model.state_dict()
        return avg_loss


    def evaluate(self, model=None):
        if model is None:
            model = self.model
    #    print("*** Generating Pseudo-Labels with Probabilities ***")

        # Create a DataLoader for the global data
        global_data_loader = DataLoader(self.global_data[self.current_iteration], batch_size=experiment_config.batch_size, shuffle=False)

        model.eval()  # Set the model to evaluation mode

        all_probs = []  # List to store the softmax probabilities
        with torch.no_grad():  # Disable gradient computation
            for inputs, _ in global_data_loader:
                inputs = inputs.to(device)
                outputs = model(inputs)  # Forward pass

                # Apply softmax to get the class probabilities
                probs = F.softmax(outputs, dim=1)  # Apply softmax along the class dimension

                all_probs.append(probs.cpu())  # Store the probabilities on CPU

        # Concatenate all probabilities into a single tensor (2D matrix)
        all_probs = torch.cat(all_probs, dim=0)

       #print(f"Shape of the 2D pseudo-label matrix: {all_probs.shape}")
        return all_probs

class Server(LearningEntity):
    def __init__(self,id_,global_data,test_data, clients_ids,clients_test_data_dict):
        LearningEntity.__init__(self, id_,global_data,test_data)

        self.num = (1000)*17
        self.pseudo_label_received = {}
        self.clusters_client_id_dict = {}
        self.clients_ids = clients_ids
        self.reset_clients_received_pl()
        self.clients_test_data_dict=clients_test_data_dict
        #if experiment_config.server_learning_technique == ServerLearningTechnique.multi_head:

        self.previous_centroids_dict = {}
        self.pseudo_label_to_send = {}
        if isinstance(experiment_config.num_clusters,int):
            num_clusters = experiment_config.num_clusters
        else:
            num_clusters = experiment_config.number_of_optimal_clusters

        self.accuracy_server_test_1 = {}
        self.accuracy_global_data_1 = {}
        self.accuracy_test_max = {}
        self.accuracy_global_max = {}

        for cluster_id in  range(num_clusters):
            self.previous_centroids_dict[cluster_id] = None

        if  experiment_config.net_cluster_technique == NetClusterTechnique.multi_head:
            self.model = get_server_model()
            self.model.apply(self.initialize_weights)

            for cluster_id in  range(num_clusters):
                self.accuracy_server_test_1[cluster_id] = {}
                self.accuracy_global_data_1[cluster_id] ={}

        if  experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
            self.multi_model_dict = {}


            for cluster_id in  range(num_clusters):
                self.multi_model_dict[cluster_id] = get_server_model()
                self.multi_model_dict[cluster_id].apply(self.initialize_weights)
                self.accuracy_server_test_1[cluster_id] = {}
                self.accuracy_global_data_1[cluster_id] ={}

        self.accuracy_per_client_1_max = {}
        for client_id in self.clients_ids:
            self.accuracy_per_client_1[client_id]={}
            self.accuracy_per_client_1_max[client_id]={}

        #self.accuracy_aggregated_head = {}
        #self.accuracy_pl_measures[cluster_id] = {}



        #self.model = get_server_model()
        #self.model.apply(self.initialize_weights)
        #self.train_learning_rate = experiment_config.learning_rate_train_s
        #self.train_epoches = experiment_config.epochs_num_train_server

        #self.weights = None





    def receive_single_pseudo_label(self, sender, info):
        self.pseudo_label_received[sender] = info

    def get_pseudo_label_list_after_models_train(self,mean_pseudo_labels_per_cluster):
        pseudo_labels_for_model_per_cluster = {}
        for cluster_id, mean_pseudo_label_for_cluster in mean_pseudo_labels_per_cluster.items():
            model_ = self.model_per_cluster[cluster_id]
            self.train(mean_pseudo_label_for_cluster, model_, str(cluster_id))
            pseudo_labels_for_model = self.evaluate(model_)
            pseudo_labels_for_model_per_cluster[cluster_id] = pseudo_labels_for_model
        ans = list(pseudo_labels_for_model_per_cluster.values())
        return ans

    def select_confident_pseudo_labels(self, cluster_pseudo_labels):
        """
        Select pseudo-labels from the cluster with the highest confidence for each data point.

        Args:
            cluster_pseudo_labels (list of torch.Tensor): List of tensors where each tensor contains pseudo-labels
                                                          from a cluster with shape [num_data_points, num_classes].

        Returns:
            torch.Tensor: A tensor containing the selected pseudo-labels of shape [num_data_points, num_classes].
        """
        num_clusters = len(cluster_pseudo_labels)
        num_data_points = cluster_pseudo_labels[0].size(0)

        # Store the maximum confidence and the corresponding cluster index for each data point
        max_confidences = torch.zeros(num_data_points, device=cluster_pseudo_labels[0].device)
        selected_labels = torch.zeros_like(cluster_pseudo_labels[0])

        for cluster_idx, pseudo_labels in enumerate(cluster_pseudo_labels):
            # Compute the max confidence for the current cluster
            cluster_max_confidences, _ = torch.max(pseudo_labels, dim=1)

            # Update selected labels where the current cluster has higher confidence
            mask = cluster_max_confidences > max_confidences
            max_confidences[mask] = cluster_max_confidences[mask]
            selected_labels[mask] = pseudo_labels[mask]

        return selected_labels
    def create_feed_back_to_clients_multihead(self,mean_pseudo_labels_per_cluster,t):
        for _ in range(experiment_config.num_rounds_multi_head):
            for cluster_id, mean_pseudo_label_for_cluster in mean_pseudo_labels_per_cluster.items():
                self.train(mean_pseudo_label_for_cluster, cluster_id)
            if experiment_config.server_feedback_technique == ServerFeedbackTechnique.similar_to_cluster:

                for cluster_id in mean_pseudo_labels_per_cluster.keys():
                        pseudo_labels_for_cluster = self.evaluate_for_cluster(cluster_id)
                        for client_id in self.clusters_client_id_dict[t][cluster_id]:
                            self.pseudo_label_to_send[client_id] = pseudo_labels_for_cluster

        if experiment_config.server_feedback_technique == ServerFeedbackTechnique.similar_to_client:
            pseudo_labels_for_cluster_list = []
            for cluster_id, mean_pseudo_label_for_cluster in mean_pseudo_labels_per_cluster.items():
                self.train(mean_pseudo_label_for_cluster, cluster_id)
            for cluster_id in mean_pseudo_labels_per_cluster.keys():
                pseudo_labels_for_cluster_list.append(self.evaluate_for_cluster(cluster_id))

            pseudo_labels_to_send = self.select_confident_pseudo_labels(pseudo_labels_for_cluster_list)

            for client_id in self.clients_ids:
                self.pseudo_label_to_send[client_id] = pseudo_labels_to_send

    def create_feed_back_to_clients_multimodel(self,mean_pseudo_labels_per_cluster,t):
        for cluster_id, mean_pseudo_label_for_cluster in mean_pseudo_labels_per_cluster.items():
            selected_model = self.multi_model_dict[cluster_id]
            for _ in range(5):
                self.train(mean_pseudo_label_for_cluster, 0,selected_model)
                if self.evaluate_accuracy(self.test_global_data, model=selected_model, k=1,
                                                cluster_id=0) == experiment_config.num_classes:
                    selected_model.apply(self.initialize_weights)

                else:
                    break
            if experiment_config.server_feedback_technique == ServerFeedbackTechnique.similar_to_cluster:
                pseudo_labels_for_cluster = self.evaluate_for_cluster(0,selected_model)
                for client_id in self.clusters_client_id_dict[t][cluster_id]:
                    self.pseudo_label_to_send[client_id] = pseudo_labels_for_cluster
        if experiment_config.server_feedback_technique == ServerFeedbackTechnique.similar_to_client:
            pseudo_labels_for_cluster_list = []
            for cluster_id, mean_pseudo_label_for_cluster in mean_pseudo_labels_per_cluster.items():
                selected_model = self.multi_model_dict[cluster_id]
                self.train(mean_pseudo_label_for_cluster, 0, selected_model)
                pseudo_labels_for_cluster_list.append(self.evaluate_for_cluster(0,selected_model))

            pseudo_labels_to_send = self.select_confident_pseudo_labels(pseudo_labels_for_cluster_list)

            for client_id in self.clients_ids:
                self.pseudo_label_to_send[client_id] = pseudo_labels_to_send
    def evaluate_results(self,t):

        if isinstance(experiment_config.num_clusters,int):
            num_clusters =experiment_config.num_clusters
        else:
            num_clusters =experiment_config.number_of_optimal_clusters

        for cluster_id in range(num_clusters):
            if experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
                selected_model = self.multi_model_dict[cluster_id]
            if experiment_config.net_cluster_technique == NetClusterTechnique.multi_head:
                selected_model = None
            if experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
                cluster_id_to_examine = 0
            else: cluster_id_to_examine = cluster_id
            self.accuracy_server_test_1[cluster_id][t] = self.evaluate_accuracy(self.test_global_data,
                                                                                model=selected_model, k=1,
                                                                                cluster_id=cluster_id_to_examine)
            #self.accuracy_global_data_1[cluster_id][t] = self.evaluate_accuracy(self.global_data,
            #                                                                    model=selected_model, k=1,
            #                                                                    cluster_id=cluster_id_to_examine)

        for client_id in self.clients_ids:
            test_data_per_clients = self.clients_test_data_dict[client_id]
            cluster_id_for_client = self.get_cluster_of_client(client_id, t)
            if experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
                print("cluster_id_for_client",cluster_id_for_client)
                print("len(self.multi_model_dict)",len(self.multi_model_dict))

                selected_model = self.multi_model_dict[cluster_id_for_client]
                cluster_id_for_client = 0

            if experiment_config.net_cluster_technique == NetClusterTechnique.multi_head:
                selected_model = None
            print("client_id",client_id,"accuracy_per_client_1")
            self.accuracy_per_client_1[client_id][t] = self.evaluate_accuracy(test_data_per_clients,
                                                                              model=selected_model, k=1,
                                                                              cluster_id=cluster_id_for_client)
            #print("client_id",client_id,"accuracy_per_client_5")
            #self.accuracy_per_client_5[client_id][t] = self.evaluate_accuracy(test_data_per_clients,
             #                                                                 model=selected_model, k=5,
             #                                                                 cluster_id=cluster_id_for_client)
            l1 = []



            for cluster_id in range(num_clusters):
                if experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
                    l1.append(self.evaluate_accuracy(self.clients_test_data_dict[client_id], model=self.multi_model_dict[cluster_id], k=1,
                                                     cluster_id=0))

                else:
                    l1.append(self.evaluate_accuracy(self.clients_test_data_dict[client_id], model=selected_model, k=1,
                                                    cluster_id=cluster_id))

            print("client_id",client_id,"accuracy_per_client_1_max",max(l1))

            self.accuracy_per_client_1_max[client_id][t] = max(l1)

    def iteration_context(self,t):
        self.current_iteration = t
        pseudo_labels_per_cluster, self.clusters_client_id_dict[t] = self.get_pseudo_labels_input_per_cluster()  # #


        if experiment_config.net_cluster_technique == NetClusterTechnique.multi_head:
            self.create_feed_back_to_clients_multihead(pseudo_labels_per_cluster,t)
        if experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
            self.create_feed_back_to_clients_multimodel(pseudo_labels_per_cluster,t)

        self.evaluate_results(t)
        self.reset_clients_received_pl()



    def train(self, mean_pseudo_labels,  cluster_num="0",selected_model=None):

        print(f"Mean pseudo-labels shape: {mean_pseudo_labels.shape}")  # Should be (num_data_points, num_classes)

        print(f"*** {self.__str__()} train *** Cluster: {cluster_num} ***")
        server_loader = DataLoader(self.global_data , batch_size=experiment_config.batch_size, shuffle=False,
                                   num_workers=0, drop_last=True)




        if selected_model is None:
            selected_model_train = self.model
        else:
            selected_model_train = selected_model

        selected_model_train.train()
        criterion = nn.KLDivLoss(reduction='batchmean')
        optimizer = torch.optim.Adam(selected_model_train.parameters(), lr=experiment_config.learning_rate_train_s)
        pseudo_targets_all = mean_pseudo_labels.to(device)

        for epoch in range(experiment_config.epochs_num_train_server):
            self.epoch_count += 1
            epoch_loss = 0

            for batch_idx, (inputs, _) in enumerate(server_loader):
                inputs = inputs.to(device)
                optimizer.zero_grad()

                # Pass `cluster_id` to the model
                outputs = selected_model_train(inputs, cluster_id=cluster_num)

                # Convert model outputs to log probabilities
                outputs_prob = F.log_softmax(outputs, dim=1)

                # Slice pseudo_targets to match the input batch size
                start_idx = batch_idx * experiment_config.batch_size
                end_idx = start_idx + inputs.size(0)
                pseudo_targets = pseudo_targets_all[start_idx:end_idx].to(device)

                # Check if pseudo_targets size matches the input batch size
                if pseudo_targets.size(0) != inputs.size(0):
                    print(
                        f"Skipping batch {batch_idx}: Expected pseudo target size {inputs.size(0)}, got {pseudo_targets.size(0)}"
                    )
                    continue

                # Normalize pseudo targets to sum to 1
                pseudo_targets = F.softmax(pseudo_targets, dim=1)

                # Calculate the loss
                loss = criterion(outputs_prob, pseudo_targets)

                # Skip batch if the loss is NaN or Inf
                if torch.isnan(loss) or torch.isinf(loss):
                    print(f"NaN or Inf loss encountered at batch {batch_idx}: {loss}")
                    continue

                loss.backward()

                # Clip gradients
                torch.nn.utils.clip_grad_norm_(selected_model_train.parameters(), max_norm=1.0)

                optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(server_loader)
            print(f"Epoch [{epoch + 1}/{experiment_config.epochs_num_train_server}], Loss: {avg_loss:.4f}")

        return avg_loss


    def reset_clients_received_pl(self):
        for id_ in self.clients_ids:
            self.pseudo_label_received[id_] = None



    def k_means_grouping(self):
        """
        Groups agents into k clusters based on the similarity of their pseudo-labels,
        with memory of cluster centroids from the previous iteration.

        Args:
            k (int): Number of clusters for k-means.

        Returns:
            dict: A dictionary where keys are cluster indices (0 to k-1) and values are lists of client IDs in that cluster.
        """
        k = experiment_config.num_clusters
        client_data = self.pseudo_label_received

        # Extract client IDs and pseudo-labels
        client_ids = list(client_data.keys())
        pseudo_labels = [client_data[client_id].flatten().numpy() for client_id in client_ids]

        # Stack pseudo-labels into a matrix for clustering
        data_matrix = np.vstack(pseudo_labels)

        # Prepare initial centroids based on previous clusters if available

        if not self.centroids_are_empty():
            # Convert previous centroids from a dictionary to a 2D array for KMeans init
            # Assuming `self.previous_centroids` is a dictionary with cluster indices as keys and centroids as values.
            # We need to extract the centroids as a list of numpy arrays and ensure it has shape (k, n_features).
            previous_centroids_array = np.array(list(self.previous_centroids_dict.values()))

            # Check if the number of centroids matches k
            if previous_centroids_array.shape[0] != k:
                raise ValueError(f"Previous centroids count does not match the number of clusters (k={k}).")

            # Initialize k-means with the previous centroids
            kmeans = KMeans(n_clusters=k, init=previous_centroids_array, n_init=1, random_state=42)
        else:
            # Default initialization
            kmeans = KMeans(n_clusters=k, random_state=42)

        # Perform clustering
        kmeans.fit(data_matrix)

        # Update centroids for the next iteration
        self.previous_centroids_dict = {i: centroid for i, centroid in enumerate(kmeans.cluster_centers_)}

        # Assign clients to clusters
        cluster_assignments = kmeans.predict(data_matrix)
        clusters = {i: [] for i in range(k)}

        # Assign client IDs to their respective clusters
        for client_id, cluster in zip(client_ids, cluster_assignments):
            clusters[cluster].append(client_id)

        return clusters

    def get_cluster_mean_pseudo_labels_dict(self,clusters_client_id_dict):
        ans = {}
        for cluster_id, clients_ids in clusters_client_id_dict.items():
            ans[cluster_id] = []
            for client_id in clients_ids:
                ans[cluster_id].append(self.pseudo_label_received[client_id])
        return ans

    def calc_L2(self,pair):
        first_pl = self.pseudo_label_received[pair[0]]
        second_pl = self.pseudo_label_received[pair[1]]
        difference = first_pl - second_pl  # Element-wise difference
        squared_difference = difference ** 2  # Square the differences
        sum_squared = torch.sum(squared_difference)  # Sum of squared differences
        return torch.sqrt(sum_squared)  # Take the square root

    def get_L2_of_all_clients(self):

        # Example list of client IDs
        pairs = list(combinations(self.clients_ids, 2))
        ans_dict = {}
        for pair in pairs:
            ans_dict[pair] = self.calc_L2(pair).item()
        return ans_dict

    def initiate_clusters_centers_dict(self,L2_of_all_clients):
        max_pair = max(L2_of_all_clients.items(), key=lambda item: item[1])
        max_pair_keys = max_pair[0]
        clusters_centers_dict = {max_pair_keys[0]: self.pseudo_label_received[max_pair_keys[0]],
                                 max_pair_keys[1]: self.pseudo_label_received[max_pair_keys[1]]}
        return clusters_centers_dict

    def update_L2_of_all_clients(self,L2_of_all_clients,clusters_centers_dict):
        L2_temp = {}
        for pair in L2_of_all_clients.keys():
            id1, id2 = pair
            if (id1 in clusters_centers_dict) ^ (id2 in clusters_centers_dict):
                L2_temp[pair] = L2_of_all_clients[pair]
            #if id1 in clusters_centers_dict:
            #    if id2 not in clusters_centers_dict:
            #        L2_temp[pair] = L2_of_all_clients[pair]
            #if id2 in clusters_centers_dict:
            #    if id1 not in clusters_centers_dict:
            #        L2_temp[pair] = L2_of_all_clients[pair]

        return L2_temp


    def get_l2_of_non_centers(self,L2_of_all_clients,clusters_centers_dict):
        all_vals = {}
        for pair, l2 in L2_of_all_clients.items():
            if pair[0] in clusters_centers_dict:
                which_of_the_two = pair[1]
            elif pair[1] in clusters_centers_dict:
                which_of_the_two = pair[0]
            if which_of_the_two not in all_vals:
                all_vals[which_of_the_two] = []
            all_vals[which_of_the_two].append(l2)

        sum_of_vals = {}
        for k,v in all_vals.items():
            sum_of_vals[k]=sum(v)
        max_key = max(sum_of_vals, key=sum_of_vals.get)

        return max_key

    def complete_clusters_centers_and_L2_of_all_clients(self,clusters_centers_dict):
        if isinstance(experiment_config.num_clusters,str):
            cluster_counter = 3
        else:
            cluster_counter =  experiment_config.num_clusters -2

        while cluster_counter > 0:
            L2_of_all_clients = self.get_L2_of_all_clients()
            L2_of_all_clients = self.update_L2_of_all_clients(L2_of_all_clients,clusters_centers_dict)
            new_center = self.get_l2_of_non_centers(L2_of_all_clients,clusters_centers_dict)
            clusters_centers_dict[new_center] = self.pseudo_label_received[new_center]
            cluster_counter = cluster_counter-1
        L2_of_all_clients = self.get_L2_of_all_clients()
        L2_of_all_clients = self.update_L2_of_all_clients(L2_of_all_clients, clusters_centers_dict)
        return L2_of_all_clients,clusters_centers_dict

    def get_l2_of_non_center_to_center(self,L2_from_center_clients,clusters_centers_dict):
        ans ={}
        for pair, l2 in L2_from_center_clients.items():
            if pair[0] in clusters_centers_dict:
                not_center = pair[1]
                center = pair[0]
            elif pair[1] in clusters_centers_dict:
                not_center = pair[0]
                center = pair[1]
            if not_center not in ans:
                ans[not_center] = {}
            ans[not_center][center] = l2
        return ans

    def get_non_center_to_which_center_dict(self,l2_of_non_center_to_center):
        one_to_one_dict = {}
        for none_center,dict_ in l2_of_non_center_to_center.items():
            one_to_one_dict[none_center] =  min(dict_, key=dict_.get)

        dict_ = one_to_one_dict
        ans = {}
        for key, value in dict_.items():
            # Add the key to the list of the corresponding value in new_dict
            if value not in ans:
                ans[value] = []  # Initialize a list for the value if not present
            ans[value].append(key)

        return ans


    def prep_clusters(self,input_):
        ans = {}
        counter = 0
        for k, list_of_other in input_.items():
            ans[counter] = [k]
            for other_ in list_of_other:
                ans[counter].append(other_)
            counter = counter + 1
        return ans




    def get_clusters_centers_dict(self):
        L2_of_all_clients = self.get_L2_of_all_clients()
        clusters_centers_dict = self.initiate_clusters_centers_dict(L2_of_all_clients)
        L2_from_center_clients,clusters_centers_dict = self.complete_clusters_centers_and_L2_of_all_clients(clusters_centers_dict)
        L2_of_non_centers = self.get_l2_of_non_center_to_center(L2_from_center_clients,clusters_centers_dict)

        non_center_to_which_center_dict = self.get_non_center_to_which_center_dict(L2_of_non_centers)
        ans = self.prep_clusters(non_center_to_which_center_dict)
        centers_to_add = self.get_centers_to_add(clusters_centers_dict,ans)
        temp_ans = {}
        if len(centers_to_add)>0:
            for cluster_id in range(max(ans.keys())+1,max(ans.keys())+1+len(centers_to_add)):
                index = cluster_id-(max(ans.keys())+1)
                temp_ans[cluster_id]=centers_to_add[index]
        for k,v in temp_ans.items():
            ans[k]=[v]



        return ans
    def get_centers_to_add(self,clusters_centers_dict,ans):
        centers_to_add =[]
        for center_id in clusters_centers_dict.keys():
            center_to_add = self.center_id_not_in_ans(ans, center_id)
            if center_to_add is not None:
                centers_to_add.append(center_to_add)
        return centers_to_add
    def center_id_not_in_ans(self,ans,center_id):
        for list_of_id in ans.values():
            if center_id in list_of_id:
                return
        return center_id



    def manual_grouping(self):
        clusters_client_id_dict = {}
        if isinstance(experiment_config.num_clusters,int):
            num_clusters = experiment_config.num_clusters
        else:
            num_clusters = experiment_config.number_of_optimal_clusters

        if num_clusters == 1:
            clusters_client_id_dict[0]=self.clients_ids
        else:
            clusters_client_id_dict =  self.get_clusters_centers_dict()
        return clusters_client_id_dict







    def get_pseudo_labels_input_per_cluster(self):
        # Stack the pseudo labels tensors into a single tensor
        mean_per_cluster = {}

        flag = False
        if experiment_config.num_clusters == "Optimal":
            clusters_client_id_dict = experiment_config.known_clusters
            flag = True
        if experiment_config.cluster_technique == ClusterTechnique.kmeans and not flag:
            clusters_client_id_dict = self.k_means_grouping()

        if experiment_config.cluster_technique == ClusterTechnique.manual  and not flag:
            clusters_client_id_dict = self.manual_grouping()

        cluster_mean_pseudo_labels_dict = self.get_cluster_mean_pseudo_labels_dict(clusters_client_id_dict)

        #if experiment_config.num_clusters>1:
        for cluster_id, pseudo_labels in cluster_mean_pseudo_labels_dict.items():
            pseudo_labels_list = list(pseudo_labels)
            if experiment_config.server_input_tech ==  ServerInputTech.mean:
                stacked_labels = torch.stack(pseudo_labels_list)
                # Average the pseudo labels across clients
                average_pseudo_labels = torch.mean(stacked_labels, dim=0)
                mean_per_cluster[cluster_id] = average_pseudo_labels
            if experiment_config.server_input_tech ==  ServerInputTech.max:
                mean_per_cluster[cluster_id] = self.select_confident_pseudo_labels(pseudo_labels_list)
        return mean_per_cluster,clusters_client_id_dict

    def evaluate_for_cluster(self, cluster_id, model=None):
        """
        Evaluate the model using the specified cluster head on the validation data.

        Args:
            cluster_id (int): The ID of the cluster head to evaluate.
            model (nn.Module, optional): The model to evaluate. Defaults to `self.model`.

        Returns:
            torch.Tensor: The concatenated probabilities for the specified cluster head.
        """
        if model is None:
            model = self.model

        print(f"*** Evaluating Cluster {cluster_id} Head ***")
        model.eval()  # Set the model to evaluation mode

        # Use the global validation data for the evaluation
        global_data_loader = DataLoader(self.global_data, batch_size=experiment_config.batch_size, shuffle=False)

        # List to store the probabilities for this cluster
        cluster_probs = []

        with torch.no_grad():  # Disable gradient computation
            for inputs, _ in global_data_loader:
                inputs = inputs.to(device)

                # Evaluate the model using the specified cluster head
                if experiment_config.net_cluster_technique == NetClusterTechnique.multi_head:
                    outputs = model(inputs, cluster_id=cluster_id)
                if experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
                    outputs = model(inputs, cluster_id=0)

                # Apply softmax to get class probabilities
                probs = F.softmax(outputs, dim=1)

                # Store probabilities for this cluster head
                cluster_probs.append(probs.cpu())

        # Concatenate all probabilities into a single tensor
        cluster_probs = torch.cat(cluster_probs, dim=0)

        return cluster_probs

    def __str__(self):
        return "server"

    def centroids_are_empty(self):
        for prev_cent in self.previous_centroids_dict.values():
            if prev_cent is None:
                return True
        else:
            return False

    def get_cluster_of_client(self,client_id,t):
        for cluster_id, clients_id_list in self.clusters_client_id_dict[t].items():
            if client_id in clients_id_list:
                return cluster_id
        print()


class Server_PseudoLabelsClusters_with_division(Server):
    def __init__(self, id_, global_data, test_data, clients_ids, clients_test_data_dict):
        Server.__init__(self, id_, global_data, test_data, clients_ids, clients_test_data_dict)

    def evaluate_for_cluster(self, cluster_id, model=None):
        """
        Evaluate the model using the specified cluster head on the validation data.

        Args:
            cluster_id (int): The ID of the cluster head to evaluate.
            model (nn.Module, optional): The model to evaluate. Defaults to `self.model`.

        Returns:
            torch.Tensor: The concatenated probabilities for the specified cluster head.
        """
        if model is None:
            model = self.model

        print(f"*** Evaluating Cluster {cluster_id} Head ***")
        model.eval()  # Set the model to evaluation mode

        # Use the global validation data for the evaluation
        global_data_loader = DataLoader(self.global_data[self.current_iteration], batch_size=experiment_config.batch_size, shuffle=False)

        # List to store the probabilities for this cluster
        cluster_probs = []

        with torch.no_grad():  # Disable gradient computation
            for inputs, _ in global_data_loader:
                inputs = inputs.to(device)

                # Evaluate the model using the specified cluster head
                if experiment_config.net_cluster_technique == NetClusterTechnique.multi_head:
                    outputs = model(inputs, cluster_id=cluster_id)
                if experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
                    outputs = model(inputs, cluster_id=0)

                # Apply softmax to get class probabilities
                probs = F.softmax(outputs, dim=1)

                # Store probabilities for this cluster head
                cluster_probs.append(probs.cpu())

        # Concatenate all probabilities into a single tensor
        cluster_probs = torch.cat(cluster_probs, dim=0)

        return cluster_probs


    def train(self, mean_pseudo_labels,  cluster_num="0",selected_model=None):

        print(f"Mean pseudo-labels shape: {mean_pseudo_labels.shape}")  # Should be (num_data_points, num_classes)

        print(f"*** {self.__str__()} train *** Cluster: {cluster_num} ***")
        server_loader = DataLoader(self.global_data[self.current_iteration] , batch_size=experiment_config.batch_size, shuffle=False,
                                   num_workers=0, drop_last=True)




        if selected_model is None:
            selected_model_train = self.model
        else:
            selected_model_train = selected_model

        selected_model_train.train()
        criterion = nn.KLDivLoss(reduction='batchmean')
        optimizer = torch.optim.Adam(selected_model_train.parameters(), lr=experiment_config.learning_rate_train_s)
        pseudo_targets_all = mean_pseudo_labels.to(device)

        for epoch in range(experiment_config.epochs_num_train_server):
            self.epoch_count += 1
            epoch_loss = 0

            for batch_idx, (inputs, _) in enumerate(server_loader):
                inputs = inputs.to(device)
                optimizer.zero_grad()

                # Pass `cluster_id` to the model
                outputs = selected_model_train(inputs, cluster_id=cluster_num)

                # Convert model outputs to log probabilities
                outputs_prob = F.log_softmax(outputs, dim=1)

                # Slice pseudo_targets to match the input batch size
                start_idx = batch_idx * experiment_config.batch_size
                end_idx = start_idx + inputs.size(0)
                pseudo_targets = pseudo_targets_all[start_idx:end_idx].to(device)

                # Check if pseudo_targets size matches the input batch size
                if pseudo_targets.size(0) != inputs.size(0):
                    print(
                        f"Skipping batch {batch_idx}: Expected pseudo target size {inputs.size(0)}, got {pseudo_targets.size(0)}"
                    )
                    continue

                # Normalize pseudo targets to sum to 1
                pseudo_targets = F.softmax(pseudo_targets, dim=1)

                # Calculate the loss
                loss = criterion(outputs_prob, pseudo_targets)

                # Skip batch if the loss is NaN or Inf
                if torch.isnan(loss) or torch.isinf(loss):
                    print(f"NaN or Inf loss encountered at batch {batch_idx}: {loss}")
                    continue

                loss.backward()

                # Clip gradients
                torch.nn.utils.clip_grad_norm_(selected_model_train.parameters(), max_norm=1.0)

                optimizer.step()
                epoch_loss += loss.item()

            avg_loss = epoch_loss / len(server_loader)
            print(f"Epoch [{epoch + 1}/{experiment_config.epochs_num_train_server}], Loss: {avg_loss:.4f}")

        return avg_loss


class Server_PseudoLabelsNoServerModel(Server):
    def __init__(self, id_, global_data, test_data, clients_ids, clients_test_data_dict):
        Server.__init__(self, id_, global_data, test_data, clients_ids, clients_test_data_dict)

    def iteration_context(self,t):
        self.current_iteration = t
        mean_pseudo_labels_per_cluster_dict, self.clusters_client_id_dict[t] = self.get_pseudo_labels_input_per_cluster()  # #


        for cluster_id,pseudo_labels_for_cluster in mean_pseudo_labels_per_cluster_dict.items():
            for client_id in self.clusters_client_id_dict[t][cluster_id]:
                self.pseudo_label_to_send[client_id] = pseudo_labels_for_cluster


class Server_Centralized(Server):
    def __init__(self,id_, train_data, test_data,evaluate_every):
        LearningEntity.__init__ (self,id_,None,None)



        self.train_data =self.break_the_dict_structure(train_data)
        self.test_data  = self.break_the_dict_structure(test_data)

        self.evaluate_every = evaluate_every

        self.num = (1000) * 17


        if experiment_config.net_cluster_technique == NetClusterTechnique.multi_head:
            raise Exception("todo")

        if experiment_config.net_cluster_technique == NetClusterTechnique.multi_model:
            self.multi_model_dict = {}

            self.accuracy_per_cluster_model = {}

            for cluster_id in self.train_data.keys():
                self.multi_model_dict[cluster_id] = get_server_model()
                self.multi_model_dict[cluster_id].apply(self.initialize_weights)
                self.accuracy_per_cluster_model[cluster_id] = {}




    def iteration_context(self,t):
        for cluster_id,model in self.multi_model_dict.items():
            self.fine_tune(model,cluster_id,self.train_data[cluster_id],self.test_data[cluster_id])


    def fine_tune(self,model,cluster_id,train,test):
        print("*** " + self.__str__() + " fine-tune ***")

        fine_tune_loader = DataLoader(train, batch_size=experiment_config.batch_size, shuffle=True)
        model.train()  # Set the model to training mode

        # Define loss function and optimizer

        criterion = nn.CrossEntropyLoss()

        optimizer = torch.optim.Adam(model.parameters(), lr=0.0001)#experiment_config.learning_rate_train_s)

        epochs = experiment_config.epochs_num_input_fine_tune_centralized_server
        for epoch in range(epochs):
            self.epoch_count += 1
            epoch_loss = 0
            for inputs, targets in fine_tune_loader:
                inputs, targets = inputs.to(device), targets.to(device)
                optimizer.zero_grad()
                outputs = model(inputs)

                loss = criterion(outputs, targets)

                # Backward pass and optimization
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
            if   epoch % self.evaluate_every == 0 and epoch!=0:
                self.accuracy_per_cluster_model[cluster_id][epoch] = self.evaluate_accuracy(test,model=model, k=1)

            result_to_print = epoch_loss / len(fine_tune_loader)
            print(f"Epoch [{epoch + 1}/{epochs}], Loss: {result_to_print:.4f}")
        #self.weights = self.model.state_dict()self.weights = self.model.state_dict()

    def break_the_dict_structure(self,data_):
        ans = {}
        if isinstance(experiment_config.num_clusters, int):
            if experiment_config.num_clusters !=1:
                raise Exception("program only 1 cluster case")

            images = []
            for group_name, torches_list in data_.items():
                for single_torch in torches_list:
                    for image in single_torch:
                        images.append(image)
            ans["group_1.0"] = transform_to_TensorDataset(images)

        else:
            if experiment_config.num_clusters != "Optimal":
                raise Exception("program only Optimal case")
            for group_name, torches_list in data_.items():
                images_per_torch_list = []
                for single_torch in torches_list:
                    for image in single_torch:
                        images_per_torch_list.append(image)
                ans[group_name] = transform_to_TensorDataset(images_per_torch_list)

        return ans

