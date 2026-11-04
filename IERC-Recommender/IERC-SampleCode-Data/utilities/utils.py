import nltk
nltk.download('averaged_perceptron_tagger')
nltk.download('maxent_ne_chunker')
nltk.download('words')
import torch
import numpy as np
from top2vec import Top2Vec
from datetime import datetime
import time
import os
import pandas as pd
import pickle
import json
from tqdm import tqdm
from transformers import BertTokenizer, BertModel
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score, mean_absolute_percentage_error
class utils:

    @classmethod
    def mean_arc_absolute_percentage_error(cls, y_true, y_pred):
        y_true = np.array(y_true)
        y_pred = np.array(y_pred)
        
        # Handle division by zero
        epsilon = np.finfo(np.float64).eps
        y_true = np.where(y_true == 0, epsilon, y_true)
        
        # Calculate APE and apply arctan
        ape = np.abs((y_true - y_pred) / y_true)
        aape = np.arctan(ape)
        
        return np.mean(aape)

    @classmethod
    def printParametersForRecommenderSystem(cls, mappingData,links,users,activities):
        interacted = {
            'user': [x[0] for x in links],
            'item': [x[1] for x in links]
        }
        interacteddf = pd.DataFrame(interacted)
        predicteddf = pd.DataFrame(mappingData).groupby('user').head(15)

        # Calculate item popularity
        item_popularity = interacteddf['item'].value_counts()

        # Normalize the popularity scores
        max_popularity = item_popularity.max()
        #normalized_popularity = item_popularity / max_popularity

        # Count of each item recommended
        item_counts = predicteddf['item'].value_counts()

        # Calculate proportions for each item
        proportions = item_counts / len(predicteddf)

        # Calculate HHI
        hhi = (proportions**2).sum()

        # Diversity score is 1 - HHI
        diversity_score = 1 - hhi
        print(f"Diversity Score: {diversity_score}")


        def item_space_coverage(data, all_items):

            recommended_items = set(data['item'])
            coverage = len(recommended_items.intersection(all_items)) / len(all_items)
            return coverage


        all_items = range(len(users),len(users)+len(activities))

        print(f"Item Space  Coverage: {item_space_coverage(predicteddf, all_items)}")

    @classmethod
    def calculate_rec_metrics(cls, df, k=10, relevance_threshold=4.0):
        # Sort dataframe by userId, and then by predicted rating descending
        df_sorted = df.sort_values(by=['userId', 'pred_rating'], ascending=[True, False])
        
        user_recalls = []
        user_ndcgs = []
        
        # Process metrics per user
        for user_id, group in df_sorted.groupby('userId'):
            
            # --- Ground Truth Information ---
            # Total number of actual relevant items for this user
            total_relevant = (group['rating'] >= relevance_threshold).sum()
            
            # If a user has no actual relevant items in the test set, skip to avoid division by zero
            if total_relevant == 0:
                continue
                
            # Extract the top-K recommendations predicted for this user
            top_k = group.head(k)
            
            # --- 1. Recall@K Calculation ---
            relevant_in_top_k = (top_k['rating'] >= relevance_threshold).sum()
            recall_at_k = relevant_in_top_k / total_relevant
            user_recalls.append(recall_at_k)
            
            # --- 2. NDCG@K Calculation ---
            # Graded actual relevance sequence in predicted order
            actual_relevances = top_k['rating'].values
            
            # Compute Discounted Cumulative Gain (DCG)
            # Using index + 2 because loop index starts at 0, matching log2(i + 1) in math
            dcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(actual_relevances))
            
            # Compute Ideal Discounted Cumulative Gain (IDCG) 
            # (The best possible DCG if sorted flawlessly by actual rating)
            ideal_relevances = sorted(group['rating'].values, reverse=True)[:k]
            idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_relevances))
            
            ndcg_at_k = dcg / idcg if idcg > 0 else 0.0
            user_ndcgs.append(ndcg_at_k)
            
        # Return the average across all valid users
        result = {
            f'Mean Recall@{k}': np.mean(user_recalls) if user_recalls else 0.0,
            f'Mean NDCG@{k}': np.mean(user_ndcgs) if user_ndcgs else 0.0
        }
        print(result)


    @classmethod
    def printErrorParametersForModelData(cls, submission):
        # Calculate MSE
        mse = mean_squared_error(submission['rating'], submission['pred_rating'])
        print(f"Mean Squared Error (MSE): {mse}")

        # Calculate MAE
        mae = mean_absolute_error(submission['rating'], submission['pred_rating'])
        print(f"Mean Absolute Error (MAE): {mae}")

        r2score = r2_score(submission['rating'], submission['pred_rating'])
        print(f"R Squared score (R2): {r2score}")

        df_filtered = submission[submission['rating'] !=0]

        mape = mean_absolute_percentage_error(df_filtered['rating'], df_filtered['pred_rating'])
        print(f"Mean absolute percentage error (MAPE): {mape}")

        maape = cls.mean_arc_absolute_percentage_error(submission['rating'], submission['pred_rating'])
        print(f"Mean Arctangent Absolute Percentage Error (MAAPE): {maape}")

        cls.calculate_rec_metrics(submission)

        # def dcg_at_k(r, k):
        #     """Compute DCG for the top k items in rank order r."""
        #     r = np.asfarray(r)[:k]
        #     return r[0] + np.sum(r[1:] / np.log2(np.arange(3, r.size + 2)))

        # def ndcg_at_k(predicted, actual):
        #     k = len(predicted)
        #     """Compute NDCG for top k items."""
        #     dcg_max = dcg_at_k(sorted(actual, reverse=True), k)
        #     if not dcg_max:
        #         return 0.
        #     return dcg_at_k(predicted, k) / dcg_max


        # ndcg = ndcg_at_k(submission['rating'], submission['pred_rating'])

        # print(f"Normalized Discounted Cumulative Gain (NDCG): {ndcg}")

    @classmethod
    def createBertEmdebbing(cls,activities, key):
        model_name = "distilbert-base-uncased"
        tokenizer = BertTokenizer.from_pretrained(model_name)
        model = BertModel.from_pretrained(model_name)

        embedding_matrix = []
        for act in activities:
            topics = ' '.join(activities[act][key])

            inputs = tokenizer(topics, return_tensors="pt", truncation=True, padding=True)
            with torch.no_grad():
                output = model(**inputs)
            word_embedding = output.last_hidden_state.mean(dim=1).squeeze().numpy()  # average over sub-tokens if any
            embedding_matrix.append(word_embedding)
        return embedding_matrix

    @classmethod
    def createTopicsFromText(cls,data,key):
        corpus = []
        for d in data:
            corpus.append(data[d][key]) 
        
        model = Top2Vec(documents=corpus, speed="learn", workers=16)
        topic_sizes1, topic_nums1 = model.get_topic_sizes()
        number_of_topics = len(topic_nums1)
        index = 0
        for d in data:

            topic_nums, topic_score, topics_words, word_scores = model.get_documents_topics([index], reduced=False,num_topics =3)

            topicswords1d = np.array(topics_words[0]).flatten()
            topicsscores1d = np.array(word_scores[0]).flatten()

            sorted_indices = sorted(enumerate(topicsscores1d), key=lambda x: x[1], reverse=True)

            # Take the indices of the top 10 values
            top_10_indices = [index[0] for index in sorted_indices[:15]]

            top_words = [topicswords1d[i] for i in top_10_indices]

            data[d][key+"_topics"] = list(set(top_words))[0:10]
            index+=1
        
        return
    
    
    @classmethod
    def generateTopicEmbeddings(cls,activities, key):
        topic_list=[]
        for act in activities:
            topic = activities[act][key]
            if(type(topic)== str):
                topic_list.append(topic)
            elif(type(topic)== list):
                for t in topic:
                    topic_list.append(t)


        all_topics = list(set(topic_list))
        topic_to_idx = {topic: i for i, topic in enumerate(all_topics)}
        return topic_to_idx
    
    @classmethod
    def createDataMatrix(cls, activities, keys):

        data = []

        for act in activities:
            val = activities[act]
            row = []
            for key in keys:
                row.append(float(val[key]))
            data.append(row)
        return np.array(data)
    
    @classmethod
    def createEmbeddingMatrix(cls,topicDic, activites, key):
        data = []
        for act in activites:
            row = activites[act][key]
            data_row=[]
            for t in topicDic:
                if(type(row) == str):
                    if(row == t):
                        data_row.append(1)
                    else:
                        data_row.append(0)
                elif(type(row) == list):
                    if(t in row):
                        data_row.append(1)
                    else:
                        data_row.append(0)
            if(len(data_row)==0):
                data_row = [0]*len(topicDic)
            data.append(data_row)
        return np.array(data)
    
    @classmethod
    def generateUserData(cls, users):
        user_data = {}
        for u in users:
            u_data = {
                "numberOfReview": len(users[u]), #user total contribution
                "average_rating": np.mean([float(x["rating"]) for x in users[u]]),
                "numberOfReviews": np.mean([x["numberOfReviews"] if "numberOfReviews" in x else 0 for x in users[u]]),
                "numofPics": np.mean([x["numofPics"] if "numofPics" in x else 0 for x in users[u]]),
                "price": np.mean([x["price"] if "price" in x else 0 for x in users[u]])
            }
            user_data[u]= u_data
        return user_data
    
    @classmethod
    def generateUserLinks(cls, users, activities,includeEmotions = False, includeNameEntities = False,emotionsPath="",nameEntityPath=""): 
        #Creates user and activity links and linkFeatures
        date_format = "%B %Y"
        users_len = len(users)
        links=[]
        links_features = []
        reduced_namedEntity = {}
        mapping = {}

        if(includeEmotions):
            f = open(emotionsPath)
            mapping = json.load(f)
            
        if(includeNameEntities):
            with open(nameEntityPath, 'rb') as f1:
                reduced_namedEntity = pickle.load(f1)

        activity_index_map = {}
        index = 0
        for act in activities:
            activity_index_map[act]= index
            index+=1

        index = 0
        for u in users:
            for act in users[u]:
                links.append((index,activity_index_map[act["activityurl"]]+users_len))

                rating = float(act["rating"])
                neg = float(act["sentiment"]["Negative"]) if act["sentiment"] != None else 0
                neutral = float(act["sentiment"]["Neutral"]) if act["sentiment"] != None else 0
                pos = float(act["sentiment"]["Positive"]) if act["sentiment"] != None else 0
                date_obj = datetime.strptime(act["date"], date_format)
                nmonth = date_obj.month/12.0
                

                matrix_data = [rating,neg,neutral,pos,nmonth]

                if(includeEmotions):                   
                    emotions = mapping[act["text"]]
                    for e in emotions:
                        matrix_data.append(emotions[e])

                if(includeNameEntities):
                   embedding = reduced_namedEntity[act["text"]]
                   for e in embedding:
                       matrix_data.append(float(e))
                   #print("embeddingLength==",len(matrix_data))


                links_features.append(matrix_data)
            
            index+=1
        
        return links, links_features
    
    @classmethod
    def getTransitActivitiesForUserFromCluster(cls, userUrl, activties, users, links, clusters,isUserUrl=True):

        activitiesIndexMapping = {}
        userIndexMapping = {}
            
        userToActivityLinkMapping = {}
        activityToUserLinkMapping = {}

        transitActivities = set()

        index = 0

        for u in users:
            userIndexMapping[index] = users[u][0]
            index+=1

        for act in activties:
            activitiesIndexMapping[index] = activties[act]
            index+=1

        for l in links:
                
            if l[0] in userToActivityLinkMapping:
                userToActivityLinkMapping[l[0]].append(l[1])
            else:
                userToActivityLinkMapping[l[0]] = [l[1]]
                    
            if l[1] in activityToUserLinkMapping:
                activityToUserLinkMapping[l[1]].append(l[0])
            else:
                activityToUserLinkMapping[l[1]] = [l[0]]


        userIndex = 0
        #get user index from url
        if(isUserUrl):
            for u in userIndexMapping:
                user = userIndexMapping[u]
                if(user['url']== userUrl):
                    userIndex=u
                    break 
        else:
            userIndex = userUrl

            #get users and activties from userCluster
        userClusterActivites = []
        userClusterUsers = []
        for c in clusters:
            cluster = clusters[c]
            if (userIndex in cluster):
                userClusterActivites = [u for u in cluster if u >= len(users)]
                userClusterUsers = [u for u in cluster if u < len(users) and u!=userIndex]
                break

            #add direct activties

        for act in userClusterActivites:
            transitActivities.add(act)


            #add activities from users in clusters
        for u in userClusterUsers:
            acts = userToActivityLinkMapping[u]

            for act in acts:
                transitActivities.add(act)


        for act in userClusterActivites:
            if act not in activityToUserLinkMapping:
                continue
            users = activityToUserLinkMapping[act]

            for u in users:
                acts2 = userToActivityLinkMapping[u]

                for act22 in acts2:
                    transitActivities.add(act22)
            
        directUserActivties = userToActivityLinkMapping[userIndex]

        for dact in directUserActivties:
            if(dact in transitActivities):
                transitActivities.remove(dact)

        activitiesLinksTuple = []

        for aa in transitActivities:
            activitiesLinksTuple.append((userIndex,aa))    

        return activitiesLinksTuple, activitiesIndexMapping

            

                

            







