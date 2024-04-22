import json

from source.transformers.base import BaseTransformer


class RuneFetchTransformerMixin(BaseTransformer):

    transformer_name = "RuneFetchTransformer"

    def transform(self, tasks):
        """
        Fetch the data from the RUNE API and save it to csvs
        :param tasks:
        :return:
        """


class OuraDocTransformer(BaseTransformer):
    transformer_name = "OuraDocTransformer"

    def transform(self, tasks):
        """
        Parse large JSONs with document batches into smaller JSONs, validating unique JSONS in the process
        :param tasks:
        :return:
        """

        time_keys = ['day', 'timestamp', 'start_datetime', 'end_datetime', '']

        for (patient, collection), filenames in tasks['todo'].items():
            collection_docs = []
            for filename in tasks['todo']:
                collection_docs.extend(json.load(filename)['data'])

            # Organize the documents for this collection by day
            date_organized = {}
            for doc in collection_docs:
                doc_date = doc['day']
                if doc_date not in date_organized:
                    date_organized[doc_date] = [doc]
                else:
                    date_organized[doc_date].append(doc)

            # Cross check these documents with the list of saved documents
            new_data = {}



            # Save each day that contains new data as a separate document
            for day, day_data in new_data.items():
                new_filename = f'{patient}_{day}_{collection}.json'
                with open(self.middle_location, new_filename) as new_out:
                    json.dump(day, new_out)
