function failures = anonymize_batch_callable(input_dir)

% anonymize all .json files in a directory, with directory structure:
% chosen_directory, must be titled 'original'
%     -> date_directories 
%         -> session_directories 
%             -> device directory (redundant)
%                 -> *.json files
%
% adds the anonymized json's into a new folder next to the 'original'
% chosen directory, titled 'anonymized_json'
%

%% anonymize

dataset_dir = input_dir;
date_list = dir(dataset_dir);
date_list = date_list(~ismember({date_list.name},{'.','..','.DS_Store'}));
failures = {};
new_dataset_dir = [dataset_dir(1:end-7), 'anonymized_json'];
mkdir(new_dataset_dir)

for date = 1:length(date_list)
    date_dir = fullfile(date_list(date).folder,...
                           date_list(date).name);
    session_list = dir(date_dir);
    session_list = session_list(~ismember({session_list.name},{'.','..','.DS_Store'}));
    
    for session = 1:length(session_list)
        
        session_dir = fullfile(session_list(session).folder,...
                             session_list(session).name);
        session_subdir = dir(session_dir);
        session_subdir = session_subdir(~ismember({session_subdir.name},...
                                    {'.','..','.DS_Store'}));
        session_subdir = fullfile(session_subdir.folder, session_subdir.name);
        json_list = dir(session_subdir);
        json_list = json_list(~ismember({json_list.name},{'.','..','.DS_Store'}));
        json_list = {json_list.name};     
        
        % check that all files exist with the correct naming convention
        required_json_files = {'AdaptiveLog', 'DeviceSettings',...
                               'DiagnosticsLog', 'ErrorLog', 'EventLog',...
                               'RawDataAccel', 'RawDataFFT',...
                               'RawDataPower', 'RawDataTD', 'StimLog',...
                               'TimeSync'};
        try  
            
            for json_file_name = required_json_files
                if ~any(strcmp(json_list,[json_file_name{1},'.json']))
                    error([json_file_name{1}, ' is missing.'])
                end
            end

            % anonymize and rename anonymized file
            rcs_anonymize(session_subdir);
            movefile(fullfile(session_dir,'DeviceNPC_Anonymized'),...
                     fullfile(new_dataset_dir, date_list(date).name, ...
                              [session_list(session).name, '_Anonymized']))       
        catch
            failures{end+1} = session_dir;
        end
    end
    
end
failures
end