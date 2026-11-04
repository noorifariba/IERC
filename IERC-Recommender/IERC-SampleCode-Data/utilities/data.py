import os
import re
import json
from json import JSONDecodeError 
from langdetect import detect, DetectorFactory
DetectorFactory.seed = 0
from textblob import TextBlob
from datetime import datetime

class data:
    CITIES = ["rome","barcelona","berlin","london","madrid","newyork","paris"]
    BASEPATH = "../data/"

    @classmethod
    def cleanPrice(cls, price):
        price_factor = 1
        if "zł" in price:
            price_factor = 4.61
        elif "Kč" in price:
            price_factor = 24.39
        elif "kr DKK" in price:
            price_factor = 7.46
        elif "$" in price or "usd" in price:
            price_factor = 1.06
        return float("".join(re.findall(r'\b\d+\.\d+\b|\b\d+\b', price)))/price_factor

    @classmethod
    def extractAirBnbData(cls):
        path = os.path.join(cls.BASEPATH,'airbnb/')
        listPath = "_AirbnbExperienceList.json"
        reviewObj = {}

        for city in cls.CITIES:
            experienceListPath = os.path.join(path,city+listPath)
            experiencePath = os.path.join(path,city)
            experienceListObj = cls.readJsonFileFromPath(experienceListPath)
            dataFiles = os.listdir(experiencePath)
            for datafile in dataFiles:
                filePath = os.path.join(experiencePath,datafile)
                index = int(datafile.replace(".json",""))
                fileJson = cls.readJsonFileFromPath(filePath)
                if(("reviews" in fileJson) and len(fileJson["reviews"])<5):
                        continue
                obj = {
                    "rating":fileJson["rating"],
                    "numberOfReviews":fileJson["numberOfReviews"],
                    "location":city,
                    "numofPics":fileJson["numofPics"],
                    "price":data.cleanPrice(fileJson["price"]),
                    "description":fileJson["description"] + " " + fileJson["locationDescription"],
                    "url":experienceListObj[index]["Url"],
                    "category": experienceListObj[index]["Categories"][-2] if len(experienceListObj[index]["Categories"])>1 else "None"
                }
                reviewObj[obj["url"]]= obj

            
        return reviewObj
    
    @classmethod
    def getAirBnbUsersData(cls,activities):
        path = os.path.join(cls.BASEPATH,'airbnb/AirBnb_UserProfiles2.json')
        with open(path, 'r') as openfile:
            json_object = json.load(openfile)

        for u in json_object:
            for ac in json_object[u]:
                if(ac["sentiment"] == None):
                    continue
                ac['rating'] = float(ac["sentiment"]["Positive"])*5
                ac["numberOfReviews"] = float(activities[ac["activityurl"]]["numberOfReviews"])
                ac["numofPics"] = float(activities[ac["activityurl"]]["numofPics"])
                ac["price"] = float(activities[ac["activityurl"]]["price"])

        return json_object


    @classmethod
    def extractTripAdvisorData(cls):
        path = os.path.join(cls.BASEPATH,'tripadvisor/')
        reviewObj = {}

        for city in cls.CITIES:
            experiencePath = os.path.join(path,city)
            dataFiles = os.listdir(experiencePath)
            for datafile in dataFiles:
                try:
                    filePath = os.path.join(experiencePath,datafile)
                    if filePath.__contains__("Users"):
                        continue
                    fileJson = cls.readJsonFileFromPath(filePath)
                    if(("reviews" in fileJson) and len(fileJson["reviews"])<5):
                        continue

                    obj = {
                        "rating":float(fileJson["rating"]),
                        "numberOfReviews": len(fileJson["reviews"]),
                        "location":city,
                        "numofPics":int(fileJson["noOfPhotos"].replace(",","")),
                        "price":data.cleanPrice(fileJson["price"].split('\n')[0]) if fileJson["price"]!=None else 0,
                        "description": str(fileJson["description"]),
                        "url":fileJson["url"],
                        "category": fileJson["popularMention"]
                    }
                    reviewObj[obj["url"]]= obj
                except JSONDecodeError:
                    pass
                except Exception as ex:
                    print(filePath)
                    raise ex
            
        return reviewObj
    
    @classmethod
    def getTripAdvisorUsersData(cls,activities):
        path = os.path.join(cls.BASEPATH,'tripadvisor/TripAdvisor_UserProfiles2.json')
        with open(path, 'r') as openfile:
            json_object = json.load(openfile)

        for u in json_object:
            for ac in json_object[u]:
                date_obj = datetime.strptime(ac["date"], "%B %d, %Y")
                ac["date"] = date_obj.strftime("%B %Y")
                if(ac["sentiment"] == None):
                    continue
                ac['rating'] = float(ac["sentiment"]["Positive"])*5
                ac["numberOfReviews"] = float(activities[ac["activityurl"]]["numberOfReviews"])
                ac["numofPics"] = float(activities[ac["activityurl"]]["numofPics"])
                ac["price"] = float(activities[ac["activityurl"]]["price"])

        return json_object
    
    @classmethod
    def extractBookingDotComData(cls):
        path = os.path.join(cls.BASEPATH,'bookingdotcom/')
        reviewObj = {}

        for city in cls.CITIES:
            experiencePath = os.path.join(path,city)
            dataFiles = os.listdir(experiencePath)
            for datafile in dataFiles:
                try:
                    filePath = os.path.join(experiencePath,datafile)
                    if filePath.__contains__("Users"):
                        continue
                    fileJson = cls.readJsonFileFromPath(filePath)
                    if(("ReviewDetails" in fileJson) and len(fileJson["ReviewDetails"])<5):
                        continue

                    obj = {
                        "rating":float(fileJson["numericReviewsStats"]["average"]) if fileJson["numericReviewsStats"]["average"]==0 else 5,
                        "numberOfReviews": len(fileJson["ReviewDetails"]),
                        "location":city,
                        "numofPics":len(fileJson["photos"]),
                        "price":fileJson["representativePrice"]["publicAmount"]/1.27, # convert GBP to USD
                        "description": str(fileJson["description"]) + " " + fileJson["additionalInfo"],
                        "url":fileJson["url"],
                        "category": [x["label"] for x in fileJson["taxonomy"]['categories']]
                    }
                    reviewObj[obj["url"]]= obj
                except JSONDecodeError:
                    pass
                except Exception as ex:
                    print(filePath)
                    raise ex
            
        return reviewObj
    
    @classmethod
    def getBookingDotComUsersData(cls,activities):
        path = os.path.join(cls.BASEPATH,'bookingdotcom/BookingDotCom_UserProfiles2.json')
        with open(path, 'r') as openfile:
            json_object = json.load(openfile)

        for u in json_object:
            for ac in json_object[u]:
                date_obj = datetime.strptime(ac["date"], "%m/%d/%Y, %H:%M:%S")
                ac["date"] = date_obj.strftime("%B %Y")
                if(ac["sentiment"] == None):
                    continue
                ac['rating'] = float(ac["sentiment"]["Positive"])*5
                ac["numberOfReviews"] = float(activities[ac["activityurl"]]["numberOfReviews"])
                ac["numofPics"] = float(activities[ac["activityurl"]]["numofPics"])
                ac["price"] = float(activities[ac["activityurl"]]["price"])

        return json_object

    @classmethod
    def getAllData(cls):
        return cls.extractAirBnbData() + cls.extractTripAdvisorData() + cls.extractBookingDotComData()

    



    @classmethod
    def readJsonFileFromPath(cls,path):
        f = open(path,"r")
        data = json.loads(f.read())
        f.close()
        return data
    
    @classmethod
    def isValidReview(cls,review):
        try:
            if(str(detect(review))=='en'):
               return True  
            else:
                return False   
        except:
            return False

