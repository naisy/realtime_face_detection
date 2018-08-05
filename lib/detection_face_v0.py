import numpy as np
from tf_utils import visualization_utils_cv2 as vis_util
from lib.session_worker import SessionWorker
from lib.load_graph_nms_v0 import LoadFrozenGraph
from lib.load_label_map import LoadLabelMap
from lib.mpvariable import MPVariable
from lib.mpvisualizeworker import MPVisualizeWorker
from lib.mpio import start_sender


import time
import cv2
import tensorflow as tf

import sys
PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3
if PY2:
    import Queue
elif PY3:
    import queue as Queue

import collections
import datetime
from lib.color_map import STANDARD_COLORS


def clip_alpha_image(background, foreground, box_x, box_y, box_w, box_h, mask_size=1.5):
    """
    resize foreground image with keep aspect ratio
    """
    # Select the pasting position with x, y
    f_h, f_w, _ = foreground.shape
    # aspect ratio
    a_h = float(box_h)/float(f_h)
    a_w = float(box_w)/float(f_w)
    if a_h > a_w:
        a_ratio = a_h
    else:
        a_ratio = a_w
    a_ratio = a_ratio*mask_size
    # resize foreground
    foreground = cv2.resize(foreground, ((int)(f_h*a_ratio), int(f_w*a_ratio)))

    """
    ajust to center
    """
    b_h, b_w, _ = background.shape
    f_h, f_w, _ = foreground.shape

    f_y = int(box_y - (f_h/4) - ((f_h/4) - box_h/2))
    f_x = int(box_x - (f_w/4) - ((f_w/4) - box_w/2))

    del_y = 0
    del_x = 0
    if f_y < 0:
        del_y = -1*f_y
        f_y = 0
    if f_x < 0:
        del_x = -1*f_x
        f_x = 0

    if f_y + f_h - del_y > b_h:
        f_h = b_h - f_y + del_y
    if f_x + f_w - del_x > b_w:
        f_w = b_w - f_x + del_x
    foreground = foreground[del_y:f_h, del_x:f_w] # cut overflow pixels
    f_h, f_w, _ = foreground.shape
    # Make a mask with transparent part 0 and opaque part 1
    alpha_mask = np.ones((f_h, f_w)) - np.clip(cv2.split(foreground)[3], 0, 1)
    # The background part of the pasting position
    target_background = background[f_y:f_y+f_h, f_x:f_x+f_w]
    #print("({},{}) ({},{}) {} {} {} {}".format(y, x, f_h, f_w, background.shape, foreground.shape, alpha_mask.shape, target_background.shape))
    # By multiplying each BRG channel by alpha_mask, the opaque part of the foreground creates new_background of [0, 0, 0]
    new_background = cv2.merge(list(map(lambda f_x:f_x * alpha_mask, cv2.split(target_background))))
    # Combine images by converting BGRA to BGR and new_background
    background[f_y:f_y+f_h, f_x:f_x+f_w] = cv2.merge(cv2.split(foreground)[:3]) + new_background
    return background


def face_detection(im_shape, boxes, classes, scores, max_boxes_to_draw=1000, min_score_thresh=0.5, use_normalized_coordinates=True):
    im_height, im_width = im_shape[:2]
    boxes = np.squeeze(boxes)
    classes = np.squeeze(classes).astype(np.int32)
    scores = np.squeeze(scores)

    box_to_display_str_map = collections.defaultdict(list)
    box_to_color_map = collections.defaultdict(str)

    faces = []
    for i in range(min(max_boxes_to_draw, boxes.shape[0])):
        if scores is not None and scores[i] > min_score_thresh:
            box = tuple(boxes[i].tolist())
            ymin, xmin, ymax, xmax = box

            if use_normalized_coordinates:
                (left, right, top, bottom) = (xmin * im_width, xmax * im_width,
                                              ymin * im_height, ymax * im_height)
            else:
                (left, right, top, bottom) = (xmin, xmax, ymin, ymax)
            faces.append([left, top, right-left, bottom-top])
    return np.int32(faces)

class FACEV0():
    def __init__(self):
        return

    def start(self, cfg):
        """ """ """ """ """ """ """ """ """ """ """
        GET CONFIG
        """ """ """ """ """ """ """ """ """ """ """
        FORCE_GPU_COMPATIBLE = cfg['force_gpu_compatible']
        SAVE_TO_MOVIE        = cfg['save_to_movie']
        VISUALIZE            = cfg['visualize']
        VIS_WORKER           = cfg['vis_worker']
        VIS_TEXT             = cfg['vis_text']
        MAX_FRAMES           = cfg['max_frames']
        WIDTH                = cfg['width']
        HEIGHT               = cfg['height']
        FPS_INTERVAL         = cfg['fps_interval']
        DET_INTERVAL         = cfg['det_interval']
        DET_TH               = cfg['det_th']
        SPLIT_MODEL          = cfg['split_model']
        LOG_DEVICE           = cfg['log_device']
        ALLOW_MEMORY_GROWTH  = cfg['allow_memory_growth']
        SPLIT_SHAPE          = cfg['split_shape']
        DEBUG_MODE           = cfg['debug_mode']
        LABEL_PATH           = cfg['label_path']
        NUM_CLASSES          = cfg['num_classes']
        FROM_CAMERA          = cfg['from_camera']
        MASK_SIZE            = cfg['mask_size']
        if FROM_CAMERA:
            VIDEO_INPUT = cfg['camera_input']
        else:
            VIDEO_INPUT = cfg['movie_input']
        """ """

        """ """ """ """ """ """ """ """ """ """ """
        LOAD FROZEN_GRAPH
        """ """ """ """ """ """ """ """ """ """ """
        load_frozen_graph = LoadFrozenGraph(cfg)
        graph = load_frozen_graph.load_graph()
        """ """

        """ """ """ """ """ """ """ """ """ """ """
        LOAD LABEL MAP
        """ """ """ """ """ """ """ """ """ """ """
        llm = LoadLabelMap()
        category_index = llm.load_label_map(cfg)
        """ """

        """ """ """ """ """ """ """ """ """ """ """
        LOAD FACE IMAGE
        """ """ """ """ """ """ """ """ """ """ """
        face_mask = cv2.imread("mask.png", -1)
        
        """ """ """ """ """ """ """ """ """ """ """
        PREPARE TF CONFIG OPTION
        """ """ """ """ """ """ """ """ """ """ """
        # Session Config: allow seperate GPU/CPU adressing and limit memory allocation
        config = tf.ConfigProto(allow_soft_placement=True, log_device_placement=LOG_DEVICE)
        config.gpu_options.allow_growth = ALLOW_MEMORY_GROWTH
        config.gpu_options.force_gpu_compatible = FORCE_GPU_COMPATIBLE
        #config.gpu_options.per_process_gpu_memory_fraction = 0.01 # 80MB memory is enough to run on TX2
        """ """

        """ """ """ """ """ """ """ """ """ """ """
        PREPARE GRAPH I/O TO VARIABLE
        """ """ """ """ """ """ """ """ """ """ """
        # Define Input and Ouput tensors
        image_tensor = graph.get_tensor_by_name('image_tensor:0')
        detection_boxes = graph.get_tensor_by_name('detection_boxes:0')
        detection_scores = graph.get_tensor_by_name('detection_scores:0')
        detection_classes = graph.get_tensor_by_name('detection_classes:0')
        num_detections = graph.get_tensor_by_name('num_detections:0')

        if SPLIT_MODEL:
            SPLIT_TARGET_NAME = ['Postprocessor/Sigmoid',
                                 'Postprocessor/ExpandDims_1',
            ]
            split_out = []
            split_in = []
            for stn in SPLIT_TARGET_NAME:
                split_out += [graph.get_tensor_by_name(stn+':0')]
                split_in += [graph.get_tensor_by_name(stn+'_1:0')]
        """ """

        """ """ """ """ """ """ """ """ """ """ """
        START WORKER THREAD
        """ """ """ """ """ """ """ """ """ """ """
        # gpu_worker uses in split_model and non-split_model
        gpu_tag = 'GPU'
        cpu_tag = 'CPU'
        gpu_worker = SessionWorker(gpu_tag, graph, config)
        if SPLIT_MODEL:
            gpu_opts = split_out
            cpu_worker = SessionWorker(cpu_tag, graph, config)
            cpu_opts = [detection_boxes, detection_scores, detection_classes, num_detections]
        else:
            gpu_opts = [detection_boxes, detection_scores, detection_classes, num_detections]
        """ """

        """
        START VISUALIZE WORKER
        """
        if VISUALIZE and VIS_WORKER:
            q_out = Queue.Queue()
            vis_worker = MPVisualizeWorker(cfg, MPVariable.vis_in_con)
            """ """ """ """ """ """ """ """ """ """ """
            START SENDER THREAD
            """ """ """ """ """ """ """ """ """ """ """
            start_sender(MPVariable.det_out_con, q_out)
        proc_frame_counter = 0
        vis_proc_time = 0

        """ """ """ """ """ """ """ """ """ """ """
        LOAD LABEL MAP
        """ """ """ """ """ """ """ """ """ """ """
        llm = LoadLabelMap()
        category_index = llm.load_label_map(cfg)
        """ """


        """ """ """ """ """ """ """ """ """ """ """
        WAIT UNTIL THE FIRST DUMMY IMAGE DONE
        """ """ """ """ """ """ """ """ """ """ """
        print('Loading...')
        sleep_interval = 0.1

        """
        PUT DUMMY DATA INTO GPU WORKER
        """
        gpu_feeds = {image_tensor:  [np.zeros((300, 300, 3))]}
        gpu_extras = {}
        gpu_worker.put_sess_queue(gpu_opts, gpu_feeds, gpu_extras)
        if SPLIT_MODEL:
            """
            PUT DUMMY DATA INTO CPU WORKER
            """
            cpu_feeds = {split_in[0]: np.zeros((1, SPLIT_SHAPE, NUM_CLASSES)),
                         split_in[1]: np.zeros((1, SPLIT_SHAPE, 1, 4))}
            cpu_extras = {}
            cpu_worker.put_sess_queue(cpu_opts, cpu_feeds, cpu_extras)
        """
        WAIT UNTIL JIT-COMPILE DONE
        """
        while True:
            g = gpu_worker.get_result_queue()
            if g is None:
                time.sleep(sleep_interval)
            else:
                break
        if SPLIT_MODEL:
            while True:
                c = cpu_worker.get_result_queue()
                if c is None:
                    time.sleep(sleep_interval)
                else:
                    break
        """ """


        """ """ """ """ """ """ """ """ """ """ """
        START CAMERA
        """ """ """ """ """ """ """ """ """ """ """
        if FROM_CAMERA:
            from lib.webcam import WebcamVideoStream as VideoReader
        else:
            from lib.video import VideoReader
        video_reader = VideoReader()
        video_reader.start(VIDEO_INPUT, WIDTH, HEIGHT, save_to_movie=SAVE_TO_MOVIE)
        frame_cols, frame_rows = video_reader.getSize()
        """ """


        """ """ """ """ """ """ """ """ """ """ """
        FONT
        """ """ """ """ """ """ """ """ """ """ """
        """ STATISTICS FONT """
        fontFace = cv2.FONT_HERSHEY_SIMPLEX
        fontScale = frame_rows/1000.0
        if fontScale < 0.4:
            fontScale = 0.4
        fontThickness = 1 + int(fontScale)


        """ """ """ """ """ """ """ """ """ """ """
        DETECTION LOOP
        """ """ """ """ """ """ """ """ """ """ """
        print('Starting Detection')
        sleep_interval = 0.005
        top_in_time = None
        try:
            while video_reader.running and MPVariable.running.value:
                if top_in_time is None:
                    top_in_time = time.time()
                """
                SPRIT/NON-SPLIT MODEL CAMERA TO WORKER
                """
                if gpu_worker.is_sess_empty(): # must need for speed
                    cap_in_time = time.time()
                    frame = video_reader.read()
                    if frame is None:
                        MPVariable.running.value = False
                        break
                    image_expanded = np.expand_dims(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), axis=0) # np.expand_dims is faster than []
                    #image_expanded = np.expand_dims(frame, axis=0) # BGR image for input. Of couse, bad accuracy in RGB trained model, but speed up.
                    cap_out_time = time.time()
                    # put new queue
                    gpu_feeds = {image_tensor: image_expanded}
                    gpu_extras = {'image':frame, 'top_in_time':top_in_time, 'cap_in_time':cap_in_time, 'cap_out_time':cap_out_time} # always image draw.
                    gpu_worker.put_sess_queue(gpu_opts, gpu_feeds, gpu_extras)

                g = gpu_worker.get_result_queue()
                if SPLIT_MODEL:
                    # if g is None: gpu thread has no output queue. ok skip, let's check cpu thread.
                    if g is not None:
                        # gpu thread has output queue.
                        result_slice_out, extras = g['results'], g['extras']
                        if cpu_worker.is_sess_empty():
                            # When cpu thread has no next queue, put new queue.
                            # else, drop gpu queue.
                            cpu_feeds = {}
                            for i in range(len(result_slice_out)):
                                cpu_feeds.update({split_in[i]:result_slice_out[i]})
                            cpu_extras = extras
                            cpu_worker.put_sess_queue(cpu_opts, cpu_feeds, cpu_extras)
                        # else: cpu thread is busy. don't put new queue. let's check cpu result queue.
                    # check cpu thread.
                    q = cpu_worker.get_result_queue()
                else:
                    """
                    NON-SPLIT MODEL
                    """
                    q = g
                if q is None:
                    """
                    SPLIT/NON-SPLIT MODEL
                    """
                    # detection is not complete yet. ok nothing to do.
                    time.sleep(sleep_interval)
                    continue

                boxes, scores, classes, num, extras = q['results'][0], q['results'][1], q['results'][2], q['results'][3], q['extras']
                det_out_time = time.time()

                """
                ALWAYS BOX DRAW ON IMAGE
                """
                vis_in_time = time.time()
                img = extras['image']
                faces = face_detection(img.shape, boxes, classes, scores)

                face_counter = 0
                for (x,y,w,h) in faces:
                    img = clip_alpha_image(img, face_mask, x, y, w, h, MASK_SIZE)
                    if DEBUG_MODE:
                        cv2.rectangle(img,(x,y),(x+w,y+h),(255,0,0),2) #draw rectangle to main image
                    face_counter += 1

                """
                DRAW FPS, TEXT
                """
                if VIS_TEXT:
                    display_str = []
                    max_text_width = 0
                    max_text_height = 0
                    display_str.append("fps: {:.1f}".format(MPVariable.fps.value))
                    display_str.append("Detection: {}".format(np.sum(face_counter)))
                    [(text_width, text_height), baseLine] = cv2.getTextSize(text=display_str[0], fontFace=fontFace, fontScale=fontScale, thickness=fontThickness)
                    x_left = int(baseLine)
                    y_top = int(text_height*1.2*3)
                    for i in range(len(display_str)):
                        [(text_width, text_height), baseLine] = cv2.getTextSize(text=display_str[i], fontFace=fontFace, fontScale=fontScale, thickness=fontThickness)
                        if max_text_width < text_width:
                            max_text_width = text_width
                        if max_text_height < text_height:
                            max_text_height = text_height
                    """ DRAW BLACK BOX """
                    cv2.rectangle(img, (x_left - 2, int(y_top)), (int(x_left + max_text_width + 2), int(y_top + len(display_str)*max_text_height*1.2+baseLine)), color=(0, 0, 0), thickness=-1)
                    """ DRAW FPS, TEXT """
                    for i in range(len(display_str)):
                        cv2.putText(img, display_str[i], org=(x_left, y_top + int(max_text_height*1.2 + (max_text_height*1.2 * i))), fontFace=fontFace, fontScale=fontScale, thickness=fontThickness, color=(77, 255, 9))

                """
                VISUALIZATION
                """
                if VISUALIZE:
                    if (MPVariable.vis_skip_rate.value == 0) or (proc_frame_counter % MPVariable.vis_skip_rate.value < 1):
                        if VIS_WORKER:
                            q_out.put({'image':img, 'vis_in_time':vis_in_time})
                        else:
                            #np.set_printoptions(precision=5, suppress=True, threshold=np.inf)  # suppress scientific float notation
                            """
                            SHOW
                            """
                            cv2.imshow("Object Detection", img)
                            # Press q to quit
                            if cv2.waitKey(1) & 0xFF == 113: #ord('q'):
                                break
                            MPVariable.vis_frame_counter.value += 1
                            vis_out_time = time.time()
                            """
                            PROCESSING TIME
                            """
                            vis_proc_time = vis_out_time - vis_in_time
                            MPVariable.vis_proc_time.value += vis_proc_time
                else:
                    """
                    NO VISUALIZE
                    """
                    for box, score, _class in zip(np.squeeze(boxes), np.squeeze(scores), np.squeeze(classes)):
                        if proc_frame_counter % DET_INTERVAL == 0 and score > DET_TH:
                            label = category_index[_class]['name']
                            print("label: {}\nscore: {}\nbox: {}".format(label, score, box))

                    vis_out_time = time.time()
                    """
                    PROCESSING TIME
                    """
                    vis_proc_time = vis_out_time - vis_in_time

                if SAVE_TO_MOVIE:
                    video_reader.save(img)

                proc_frame_counter += 1
                if proc_frame_counter > 100000:
                    proc_frame_counter = 0
                """
                PROCESSING TIME
                """
                top_in_time = extras['top_in_time']
                cap_proc_time = extras['cap_out_time'] - extras['cap_in_time']
                gpu_proc_time = extras[gpu_tag+'_out_time'] - extras[gpu_tag+'_in_time']
                if SPLIT_MODEL:
                    cpu_proc_time = extras[cpu_tag+'_out_time'] - extras[cpu_tag+'_in_time']
                else:
                    cpu_proc_time = 0
                lost_proc_time = det_out_time - top_in_time - cap_proc_time - gpu_proc_time - cpu_proc_time
                total_proc_time = det_out_time - top_in_time
                MPVariable.cap_proc_time.value += cap_proc_time
                MPVariable.gpu_proc_time.value += gpu_proc_time
                MPVariable.cpu_proc_time.value += cpu_proc_time
                MPVariable.lost_proc_time.value += lost_proc_time
                MPVariable.total_proc_time.value += total_proc_time

                if DEBUG_MODE:
                    if SPLIT_MODEL:
                        sys.stdout.write('snapshot FPS:{: ^5.1f} total:{: ^10.5f} cap:{: ^10.5f} gpu:{: ^10.5f} cpu:{: ^10.5f} lost:{: ^10.5f} | vis:{: ^10.5f}\n'.format(
                            MPVariable.fps.value, total_proc_time, cap_proc_time, gpu_proc_time, cpu_proc_time, lost_proc_time, vis_proc_time))
                    else:
                        sys.stdout.write('snapshot FPS:{: ^5.1f} total:{: ^10.5f} cap:{: ^10.5f} gpu:{: ^10.5f} lost:{: ^10.5f} | vis:{: ^10.5f}\n'.format(
                            MPVariable.fps.value, total_proc_time, cap_proc_time, gpu_proc_time, lost_proc_time, vis_proc_time))
                """
                EXIT WITHOUT GUI
                """
                if not VISUALIZE:
                    if proc_frame_counter >= MAX_FRAMES:
                        MPVariable.running.value = False
                        break

                """
                CHANGE SLEEP INTERVAL
                """
                if MPVariable.frame_counter.value == 0 and MPVariable.fps.value > 0:
                    sleep_interval = 0.1 / MPVariable.fps.value
                    MPVariable.sleep_interval.value = sleep_interval
                MPVariable.frame_counter.value += 1
                top_in_time = None
            """
            END while
            """
        except:
            import traceback
            traceback.print_exc()
        finally:
            """ """ """ """ """ """ """ """ """ """ """
            CLOSE
            """ """ """ """ """ """ """ """ """ """ """
            if VISUALIZE and VIS_WORKER:
                q_out.put(None)
            MPVariable.running.value = False
            gpu_worker.stop()
            if SPLIT_MODEL:
                cpu_worker.stop()
            video_reader.stop()

            if VISUALIZE:
                cv2.destroyAllWindows()
            """ """

        return

