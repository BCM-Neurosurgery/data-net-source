import sys


def do_2d_pose(video_source, output):
    try:
        try:
            # location of the openpose python package
            sys.path.append('/home/weill1/openpose')
            from openpose import pyopenpose as op
        except ImportError as e:
            print(
                'Error: OpenPose library could not be found. Did you enable `BUILD_PYTHON` in CMake and have this Python script in the right folder?')
            raise e

        # Custom Params (refer to include/openpose/flags.hpp for more parameters)
        config = {
            "model_folder": "../../../models/",
            "face": False,
            "hand": True,
            "video": video_source,
            "write_json": output,
            "display": 0
        }

        # Starting OpenPose
        opWrapper = op.WrapperPython(op.ThreadManagerMode.Synchronous)
        opWrapper.configure(config)
        opWrapper.execute()

    except Exception as e:
        print(e)
        sys.exit(-1)


def do_3d_pose():
    pass


def upload_pose():
    pass


if __name__ == "__main__":
    do_2d_pose('/media/test/PoseShort.avi', '/media/test/output/')