# import configuration here 


class OuraChecker:
    def __init__(self):
        # load configuration -> need the following:
        # oura_api_key 
        # webhook_comms directory (directory that webhook listener writes to)
        # oura_output directory (directory to save oura data to)
        pass
        
    def check_posts(self):
        # check if there are any new posts in webhook_comms
            # if there's a new post
                # call self.request_oura_data(event_data)
                # if the data is valid
                    # call self.save_oura_data(json_data, timestamp)
        pass
    
    def request_oura_data(self, event_data):
        # if there's a new post, ask oura for the data
        pass
        
    def save_oura_data(self, json_data, timestamp):
        # if there's new data, save the data as a JSON file
        pass
    
    def run(self):
        self.check_posts()
        pass 