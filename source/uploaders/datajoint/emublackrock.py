import json
import pathlib
import re
import sys
import traceback

from datajoint import DataJointError
from datajoint.errors import DuplicateError

from source.uploaders.datajoint import DataJointUploader


class EMUBlackrockDJUploader(DataJointUploader):

    target_location = {
        'sql-config': {
            'host': 'localhost',
            'username': '<USERNAME>',
            'password': '<PASSWORD>',
            'port': 0000,
            'stores': {},
        },
        'patient_config': 'path/to/toml/with/patient/info'
    }

    uploader_name = 'EMUNSPDataJointUploader'
    parsed_filetypes = ['nev', 'ns3', 'ns5']
    destination = None

    def lookup(self, dj_table, primary_keys, search, squash=True):
        """Search for and return the primary keys for one entry in a table"""
        query = dj_table & search
        matches = query.fetch(*primary_keys)
        if len(matches) == 0:
            raise DataJointError(f'No matching entry in table {dj_table}!')
        elif len(matches) == 1:
            return matches[0]
        elif squash:
            self.warning(f'Found {len(matches)} matching entries. Returning only the first!')
            return matches[0]
        else:
            raise DataJointError(f'Lookup expected exactly one entry, found {len(matches)}!')

    def get_patient_info(self, patient_emu_id):
        import toml
        with open(self.target_location['patient_config']) as f:
            all_patient_info = toml.load(f)
        return all_patient_info[patient_emu_id]

    def upload(self, ready):

        successes, errors, skipped = [], [], []
        self.connect_to_database()
        # Define the schema to use by importing the appropriate script
        from emu24 import schema

        for filename in ready['to upload']:
            self.debug('Processing file {}'.format(filename))

            # TODO: move these to checkers after we merge with oura-updates and config file improvements
            # Skip files that are not in a DATA directory
            if 'DATA' not in filename:
                continue
            filename = pathlib.Path(filename).as_posix()
            filetype = filename.split('.')[-1]
            if filetype not in self.parsed_filetypes:
                # Skip file types that are not listed as parsable
                continue

            try:
                # Get the patient ID in the database based on the EMU patient ID
                patient = re.search(r'([A-Z]*)Datafile', filename).group(1)  # Patient name decoded from the file path
                try:
                    patient_id = self.lookup(
                        schema.Patient(),
                        ['patient_id'],
                        f"emu_id='{patient}'"
                    )
                except DataJointError as e:
                    self.warning(f'Failed to look up patient: {e}')
                    self.warning('Making a new patient+admission from the config file info')
                    new_pid = len(schema.Patient()) + 1
                    patient_info = self.get_patient_info(patient)
                    schema.Patient().insert1({
                        'patient_id': new_pid,
                        'dob': patient_info['birthdate'],
                        'emu_id': patient
                    })
                    patient_id = new_pid

                    query = (schema.Admission & f"patient_id='{new_pid}'")
                    new_admission_pk = query.fetch('admission_id').size + 1
                    schema.Admission().insert1({
                        'patient_id': new_pid,
                        'admission_id':new_admission_pk,
                        'admission_date': patient_info['admitdate'],
                    })

                # Assume that we want the id of most recent admission
                query = schema.Admission() & f"patient_id='{patient_id}'"
                admissions = query.fetch()
                sort_ready = [(date, id) for (_, id, date) in admissions]
                by_date = [id for (date, id) in sorted(sort_ready, key=lambda pair: pair[0])]
                admission_id = by_date[-1]

                # Get the ID of this toc instance, or make a new one if necessary
                toc_name = re.search(r'Datafile/DATA/([0-9-]*)/', filename).group(1)
                try:
                    toc_id = self.lookup(
                        schema.TOCInstance(),
                        ['toc_id'],
                        f"patient_id='{patient_id}' AND admission_id='{admission_id}' AND base_file='{toc_name}'",
                        squash=True
                    )
                except DataJointError as e:
                    self.warning(f'Got an error while looking up the TOC instance: {e}')
                    self.warning('Making a new TOC mode instance')
                    new_toc_id = len(schema.TOCInstance())
                    schema.TOCInstance().insert1({
                        'patient_id': patient_id,
                        'admission_id': admission_id,
                        'toc_id': new_toc_id,
                        'base_file': toc_name
                    })
                    toc_id = new_toc_id

                # Get the NSP and Chunk IDs from the filename
                chunk_data = re.search(r'NSP([12])-[0-9-]*-([0-9]{3})\.[nsev0-9]{3}', filename)
                nsp_id = chunk_data.group(1)
                chunk_id = chunk_data.group(2)

                # Insert into the appropriate table based on the file type
                file_table = getattr(schema, f'{filetype.upper()}Chunks')
                try:
                    file_table.insert1({
                        'patient_id': patient_id,
                        'admission_id': admission_id,
                        'toc_id': toc_id,
                        'nsp_id': nsp_id,
                        'chunk_id': chunk_id,
                        f'{filetype.lower()}_file': filename,
                    })
                    self.info(f'Added: {filetype} for {patient} at {toc_name} NSP{nsp_id} chunk {chunk_id}')
                except DuplicateError:
                    msg = f'Already in DB: {filetype} for {patient} at {toc_name} NSP{nsp_id} chunk {chunk_id}'
                    self.info(msg)
                    skipped.append({
                        'type': 'Already in DB',
                        'filename': filename,
                        'destination': self.destination,
                        'info': msg
                    })

            except Exception as e:
                error_dict = {
                    'type': 'upload failure',
                    'location': 'CopyUploaderMixin.upload',
                    'filename': filename,
                    'destination': self.destination,
                    'error': str(e),
                    'trace': traceback.format_exception(*sys.exc_info())
                }
                errors.append(error_dict)
                self.warning(f'An upload failed! \n {json.dumps(error_dict, skipkeys=True, indent=2)}')
            else:
                successes.append({
                    'type': 'upload success',
                    'filename': filename,
                    'destination': self.destination,
                })
        return {
            'success': successes, 'failure': errors, 'skipped': skipped
        }
