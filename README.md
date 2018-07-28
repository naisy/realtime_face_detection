# Tensorflow Realtime Face Detection

## Getting Started:
- edit `config.yml` for your environment. (Ex. video_input: 0 # for PC)
- run `python run_stream.py` realtime object detection from webcam (Multi-Threading)
- or run `python run_video.py` realtime object detection from movie file (Multi-Threading)

## Requirements:
```
pip install --upgrade pyyaml
```
Also, OpenCV >= 3.1 and Tensorflow >= 1.4 (1.6 is good)

## config.yml
* Model type  
```
model_type: 'face_v0'
```

* Face image size
Mask image size can change.
```
mask_size: 1.5
```

* See also  
[https://github.com/naisy/realtime_object_detection](https://github.com/naisy/realtime_object_detection)


## Related: Tensorflow Realtime Object Detection
[https://github.com/naisy/realtime_object_detection](https://github.com/naisy/realtime_object_detection)

<hr>

## License and Information
mask.png: Non-commercial. Internet use only. [笑い男マーク](http://commons.nicovideo.jp/material/nc73730)<br>
Model: Apache 2.0 [Tensorflow Face Detector](https://github.com/yeephycho/tensorflow-face-detection)<br>
Face Dataset: [WIDER FACE](http://mmlab.ie.cuhk.edu.hk/projects/WIDERFace/index.html)<br>