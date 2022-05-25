function failures = convert_json_batch_callable(input_dir)

% convert all .json files in a subdirectory structure following the format:
% data_directory 
%     -> date_directories 
%         -> session_directories 
%             -> *.json files
%
% and saves them as .csv or .mat files with the format:
% data_directory_[csv/mat] (in the same outer directory as the original 
%                           data_directory)
%     -> date_directories
%         -> *.csv files
% where the .csv or .mat file is named the same way as the session 
% directory


%% create new directory for the .mat files and fill it with converted .json

dataset_dir = input_dir;
new_dataset_dir = [dataset_dir, '_csv'];
mkdir(new_dataset_dir)
date_list = dir(dataset_dir);
date_list = date_list(~ismember({date_list.name},{'.','..','.DS_Store'}));

failures = {};

for date = 1:length(date_list)
    date_dir = fullfile(dataset_dir,...
        date_list(date).name);
    new_date_dir = fullfile(new_dataset_dir,...
        date_list(date).name);
    mkdir(new_date_dir)
    session_list = dir(date_dir);
    session_list = session_list(~ismember({session_list.name},{'.','..','.DS_Store'}));

    for session = 1:length(session_list)
        % process the data into a combined data table
        session_dir = session_list(session).name;
        save_location = new_date_dir;
        session_dir = fullfile(date_dir, session_dir);
        try
            save_session_as_csv(session_dir, save_location)
        catch
            failures{end+1} = session_dir;
        end
    end

end

failures


end


function [] = save_session_as_csv(session_dir, save_location)
try
    [unifiedDerivedTimes,...
        timeDomainData, timeDomainData_onlyTimeVariables, timeDomain_timeVariableNames,...
        AccelData, AccelData_onlyTimeVariables, Accel_timeVariableNames,...
        PowerData, PowerData_onlyTimeVariables, Power_timeVariableNames,...
        FFTData, FFTData_onlyTimeVariables, FFT_timeVariableNames,...
        AdaptiveData, AdaptiveData_onlyTimeVariables, Adaptive_timeVariableNames,...
        timeDomainSettings, powerSettings, fftSettings, eventLogTable,...
        metaData, stimSettingsOut, stimMetaData, stimLogSettings,...
        DetectorSettings, AdaptiveStimSettings, AdaptiveEmbeddedRuns_StimSettings,...
        versionInfo] = ProcessRCS(session_dir, 2);
catch

    session_dir(end-40:end)
end
% Prep save location
switch metaData.INSimplantLocation
    case 'Left chest'
        hemisphere = {'left'};
    case 'Right chest'
        hemisphere = {'right'};
end
rec_start = num2str(unifiedDerivedTimes(1));
rec_end = num2str(unifiedDerivedTimes(end));
recordingFolder = ['rcs_', hemisphere{1}, '_', rec_start, '_', rec_end];
mkdir(save_location, recordingFolder)

% Prepare  and write the neural time domain data
if ~isempty(timeDomainData)
    readyNeural = removevars(timeDomainData, {'localTime', 'samplerate'});
    prev_var_name = '';
    for td_chan = 1:4
        var_name = ['time_domain_', ...
            timeDomainSettings.TDsettings{1,1}(td_chan).plusInput, '_',...
            timeDomainSettings.TDsettings{1,1}(td_chan).minusInput];
        if strcmp(var_name, prev_var_name)
            readyNeural.Properties.VariableNames{td_chan} = ...
                [var_name, '_a'];
            readyNeural.Properties.VariableNames{td_chan + 1} = ...
                [var_name, '_b'];
        else
            readyNeural.Properties.VariableNames{td_chan + 1} = ...
                var_name;
        end
        prev_var_name = var_name;
    end
    readyNeural.Properties.VariableNames{1} = 'timestamp';
    writetable(readyNeural, ...
        fullfile(save_location, recordingFolder, 'NeuralTimeDomain.csv'))
end

% prepare and write the accelerometer data
if ~isempty(AccelData)
    readyAccel = removevars(AccelData, {'localTime', 'samplerate'});
    readyAccel.Properties.VariableNames = { ...
        'timestamp', 'accel_x', 'accel_y', 'accel_z'...
    };
    writetable(readyAccel, ...
        fullfile(save_location, recordingFolder, 'AccelTimeDomain.csv'))
end

% power band channels
if ~isempty(PowerData)
    readyPower = removevars(PowerData, ...
        {'localTime', 'TDsamplerate', 'samplerate', 'FftSize', 'ValidDataMask', 'ExternalValuesMask'});
    readyPower.Properties.VariableNames{'newDerivedTime'} = 'timestamp';
    writetable(readyPower, ...
        fullfile(save_location, recordingFolder, 'NeuralPowerBands.csv'))
end

% fft channel IN PROGRESS
if ~isempty(FFTData)
    readyFFT = removevars(FFTData, {});
    writetable(readyFFT, ...
        fullfile(save_location, recordingFolder, 'NeuralFFT.csv'));
end

% adaptive channels
if ~isempty(AdaptiveData)
    readyAdaptive = removevars(AdaptiveData, ...
        {'localTime', 'samplerate'});
    readyAdaptive.Properties.VariableNames{'newDerivedTime'} = 'timestamp';
    writetable(readyAdaptive, ...
        fullfile(save_location, recordingFolder, 'AdaptiveStim.csv'))
end

% Stim mode changes
if ~isempty(AdaptiveEmbeddedRuns_StimSettings)
    readyStimModes = removevars(AdaptiveEmbeddedRuns_StimSettings, ...
        {'deltas', 'states', 'deltaLimitsValid', 'deltasValid'});
    readyStimModes.Properties.VariableNames{'HostUnixTime'} = 'timestamp';
    writetable(readyStimModes, ...
        fullfile(save_location, recordingFolder, 'StimModeChanges.csv'))
end

% Stim log
if ~isempty(stimLogSettings)
    readyStimLog = removevars(stimLogSettings, ...
        {'updatedParameters', 'GroupA', 'GroupB', 'GroupC', 'GroupD'});
    readyStimLog.Properties.VariableNames{'HostUnixTime'} = 'timestamp';
    writetable(readyStimLog, ...
        fullfile(save_location, recordingFolder, 'StimLog.csv'))
end

% Event Log
if ~isempty(eventLogTable)
    readyEvents = removevars(eventLogTable, ...
        {'SessionId', 'UnixOnsetTime', 'UnixOffsetTime'});
    readyEvents.Properties.VariableNames{'HostUnixTime'} = 'timestamp';
    for i = 1:length(readyEvents.EventSubType)
        clean = regexprep(readyEvents.EventSubType(i), ...
            '[\r\n,]', ' ');
        readyEvents.EventSubType(i) = cellstr(clean);
    end
    writetable(readyEvents, ...
        fullfile(save_location, recordingFolder, 'EventLog.csv'))
end

% Prepare and write the settings json
TDsource = timeDomainSettings.TDsettings;
PDsource = powerSettings.powerBands;
FFTsource = powerSettings.fftConfig;
rec_setting_list = cell(length(TDsource),1);
for rec = 1:length(TDsource)
    rec_data = TDsource{rec,1};
    ch_list = cell(4,1);
    for channel = 1:4
        ch_settings = struct(...
            'gain', rec_data(channel).gain, ...
            'sense_contacts', rec_data(channel).chanOut, ...
            'high_pass', rec_data(channel).hpf / 10, ...
            'low_pass_a', rec_data(channel).lpf1, ...
            'low_pass_b', rec_data(channel).lpf2 ...
            );
        ch_list{channel} = ch_settings;
    end
    rec_settings = struct(...
        'start', num2str(timeDomainSettings.timeStart(rec)), ...
        'end', num2str(timeDomainSettings.timeStop(rec)), ...
        'neuralTD_samplerate', timeDomainSettings.samplingRate(rec), ...
        'channel_settings', {ch_list}, ...
        'power_domain_settings', {PDsource(rec)}, ...
        'fft_settings', {FFTsource(rec)}...
    );
    rec_setting_list{rec} = rec_settings;
end
detect_settings = struct( ...
    'LD0', DetectorSettings.Ld0, ...
    'LD1', DetectorSettings.Ld1 ...
    );
settings = struct( ...
    'start', rec_start, ...
    'time_zone', metaData.UTCoffset, ...
    'hemisphere', hemisphere, ...
    'stim_meta', stimMetaData, ... 
    'recording_settings', {rec_setting_list}, ...
    'detector_settings', detect_settings);
json = jsonencode(settings);
clean_json = strrep(json, "%", "percent");
fid = fopen(fullfile(save_location, recordingFolder, 'BaseSettings.json'), 'wt');
fprintf(fid, clean_json);
fclose(fid);

end


