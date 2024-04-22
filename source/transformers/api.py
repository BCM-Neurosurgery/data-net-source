import json
import os.path

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

        with open(os.path.join(self.middle_location, 'upload_state.json')) as state_file:
            upload_state = json.load(state_file)

        for (patient, collection), filenames in tasks['to do'].items():
            collection_docs = []
            for filename in filenames:
                with open(filename) as source:
                    collection_docs.extend(json.load(source)['data'])

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
            for date, day_data in date_organized.items():
                uploaded = [
                    upload for upload in upload_state
                    if upload['patient'] == patient and upload['collection'] == collection and upload['date'] == date
                ]
                # We found no matching data for this day, so upload by default
                if not uploaded:
                    new_data[date] = day_data
                    break

                # Get all the previously uploaded document ids for this day
                uploaded_docs = []
                for upload in uploaded:
                    uploaded_docs.extend(upload['documents'])

                # There are more documents for this day than we uploaded before
                if len(uploaded_docs) < len(day_data):
                    new_data[date] = day_data
                    break

                # Check all the doc ids individually
                found_new = False
                for doc in day_data:
                    if doc['id'] not in uploaded_docs:
                        new_data[date] = day_data
                        found_new = True
                        break
                if found_new:
                    break

                # We only reach this point if there is nothing new to upload
                self.notify(f'No new data to upload for {date}')

            # Save each day that contains new data as a separate document
            for day, day_data in new_data.items():
                new_filename = f'{patient}_{day}_{collection}.json'
                with open(self.middle_location, 'parsed', new_filename) as new_out:
                    json.dump(day, new_out)
