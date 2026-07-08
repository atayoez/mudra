"""MediaPipe palm-detection + hand-landmark models via OpenCV dnn (no PyTorch,
no pip — runs on distro python3-opencv alone).

Adapted from the OpenCV Model Zoo (Apache-2.0):
  https://github.com/opencv/opencv_zoo
    models/palm_detection_mediapipe/mp_palmdet.py
    models/handpose_estimation_mediapipe/mp_handpose.py
The 2016-entry SSD anchor table is generated instead of hardcoded (verified
identical to the zoo's literal table).

Landmarks follow the MediaPipe 21-keypoint hand convention (wrist=0,
thumb tip=4, index tip=8, middle tip=12, ring tip=16, pinky tip=20).
"""
import cv2 as cv
import numpy as np


def _palm_anchors():
    # SSD anchor centers for the 192x192 palm model:
    # stride-8 24x24 grid x2 anchors, stride-16 12x12 grid x6 anchors.
    out = []
    for grid, n in ((24, 2), (12, 6)):
        for y in range(grid):
            for x in range(grid):
                out += [[(x + 0.5) / grid, (y + 0.5) / grid]] * n
    return np.array(out, np.float32)


class MPPalmDet:
    """Palm detector: full frame -> palm boxes + 7 rough palm landmarks."""

    def __init__(self, model_path, score_threshold=0.6, nms_threshold=0.3):
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.input_size = np.array([192, 192])  # wh
        self.model = cv.dnn.readNet(model_path)
        self.anchors = _palm_anchors()

    def _preprocess(self, image):
        pad_bias = np.array([0., 0.])  # left, top
        ratio = min(self.input_size / image.shape[:2])
        if image.shape[:2] != tuple(self.input_size):
            ratio_size = (np.array(image.shape[:2]) * ratio).astype(np.int32)
            image = cv.resize(image, (ratio_size[1], ratio_size[0]))
            pad_h = self.input_size[0] - ratio_size[0]
            pad_w = self.input_size[1] - ratio_size[1]
            pad_bias[0] = left = pad_w // 2
            pad_bias[1] = top = pad_h // 2
            image = cv.copyMakeBorder(image, top, pad_h - top, left,
                                      pad_w - left, cv.BORDER_CONSTANT,
                                      None, (0, 0, 0))
        image = cv.cvtColor(image, cv.COLOR_BGR2RGB)
        image = image.astype(np.float32) / 255.0
        pad_bias = (pad_bias / ratio).astype(np.int32)
        return image[np.newaxis, :, :, :], pad_bias  # hwc -> nhwc

    def infer(self, image):
        """Returns (N, 19) rows: [x1,y1,x2,y2, 7*(x,y) landmarks, score]."""
        h, w, _ = image.shape
        input_blob, pad_bias = self._preprocess(image)
        self.model.setInput(input_blob)
        output_blob = self.model.forward(
            self.model.getUnconnectedOutLayersNames())
        return self._postprocess(output_blob, np.array([w, h]), pad_bias)

    def _postprocess(self, output_blob, original_shape, pad_bias):
        score = output_blob[1][0, :, 0]
        box_delta = output_blob[0][0, :, 0:4]
        landmark_delta = output_blob[0][0, :, 4:]
        scale = max(original_shape)

        score = 1 / (1 + np.exp(-score.astype(np.float64)))

        cxy_delta = box_delta[:, :2] / self.input_size
        wh_delta = box_delta[:, 2:] / self.input_size
        xy1 = (cxy_delta - wh_delta / 2 + self.anchors) * scale
        xy2 = (cxy_delta + wh_delta / 2 + self.anchors) * scale
        boxes = np.concatenate([xy1, xy2], axis=1)
        boxes -= [pad_bias[0], pad_bias[1], pad_bias[0], pad_bias[1]]
        keep_idx = cv.dnn.NMSBoxes(boxes, score, self.score_threshold,
                                   self.nms_threshold)
        if len(keep_idx) == 0:
            return np.empty(shape=(0, 19))
        selected_score = score[keep_idx]
        selected_box = boxes[keep_idx]

        selected_landmarks = landmark_delta[keep_idx].reshape(-1, 7, 2)
        selected_landmarks = (selected_landmarks / self.input_size
                              + self.anchors[keep_idx][:, np.newaxis, :])
        selected_landmarks *= scale
        selected_landmarks -= pad_bias

        return np.c_[selected_box.reshape(-1, 4),
                     selected_landmarks.reshape(-1, 14),
                     selected_score.reshape(-1, 1)]


class MPHandPose:
    """Hand landmarker: frame + palm row -> 21 precise hand landmarks."""

    PALM_LANDMARK_IDS = (0, 5, 9, 13, 17, 1, 2)  # hand-landmark ids of the
    #                                              palm detector's 7 points
    PALM_BOX_PRE_SHIFT_VECTOR = [0, 0]
    PALM_BOX_PRE_ENLARGE_FACTOR = 4
    PALM_BOX_SHIFT_VECTOR = [0, -0.4]
    PALM_BOX_ENLARGE_FACTOR = 3

    def __init__(self, model_path, conf_threshold=0.8):
        self.conf_threshold = conf_threshold
        self.input_size = np.array([224, 224])  # wh
        self.model = cv.dnn.readNet(model_path)

    def _crop_and_pad_from_palm(self, image, palm_bbox, for_rotation=False):
        wh_palm_bbox = palm_bbox[1] - palm_bbox[0]
        shift = (self.PALM_BOX_PRE_SHIFT_VECTOR if for_rotation
                 else self.PALM_BOX_SHIFT_VECTOR) * wh_palm_bbox
        palm_bbox = palm_bbox + shift
        center = np.sum(palm_bbox, axis=0) / 2
        wh_palm_bbox = palm_bbox[1] - palm_bbox[0]
        enlarge = (self.PALM_BOX_PRE_ENLARGE_FACTOR if for_rotation
                   else self.PALM_BOX_ENLARGE_FACTOR)
        half = wh_palm_bbox * enlarge / 2
        palm_bbox = np.array([center - half, center + half]).astype(np.int32)
        palm_bbox[:, 0] = np.clip(palm_bbox[:, 0], 0, image.shape[1])
        palm_bbox[:, 1] = np.clip(palm_bbox[:, 1], 0, image.shape[0])
        image = image[palm_bbox[0][1]:palm_bbox[1][1],
                      palm_bbox[0][0]:palm_bbox[1][0], :]
        # pad to square so corner pixels survive the rotation
        side_len = int(np.linalg.norm(image.shape[:2]) if for_rotation
                       else max(image.shape[:2]))
        pad_h = side_len - image.shape[0]
        pad_w = side_len - image.shape[1]
        left = pad_w // 2
        top = pad_h // 2
        image = cv.copyMakeBorder(image, top, pad_h - top, left, pad_w - left,
                                  cv.BORDER_CONSTANT, None, (0, 0, 0))
        bias = palm_bbox[0] - [left, top]
        return image, palm_bbox, bias

    def _preprocess(self, image, palm):
        pad_bias = np.array([0, 0], dtype=np.int32)  # left, top
        palm_bbox = palm[0:4].reshape(2, 2)
        image, palm_bbox, bias = self._crop_and_pad_from_palm(
            image, palm_bbox, True)
        image = cv.cvtColor(image, cv.COLOR_BGR2RGB)
        pad_bias += bias

        # rotate so the hand is vertical (wrist below middle-finger base)
        palm_bbox = palm_bbox - pad_bias
        palm_landmarks = palm[4:18].reshape(7, 2) - pad_bias
        p1 = palm_landmarks[0]  # palm base (wrist)
        p2 = palm_landmarks[2]  # middle finger base
        radians = np.pi / 2 - np.arctan2(-(p2[1] - p1[1]), p2[0] - p1[0])
        radians -= 2 * np.pi * np.floor((radians + np.pi) / (2 * np.pi))
        angle = np.rad2deg(radians)
        center = np.sum(palm_bbox, axis=0) / 2
        rotation_matrix = cv.getRotationMatrix2D(center, angle, 1.0)
        rotated_image = cv.warpAffine(image, rotation_matrix,
                                      (image.shape[1], image.shape[0]))
        coords = np.c_[palm_landmarks, np.ones(palm_landmarks.shape[0])]
        rotated_palm_landmarks = np.array([
            np.dot(coords, rotation_matrix[0]),
            np.dot(coords, rotation_matrix[1])])
        rotated_palm_bbox = np.array([
            np.amin(rotated_palm_landmarks, axis=1),
            np.amax(rotated_palm_landmarks, axis=1)])

        crop, rotated_palm_bbox, _ = self._crop_and_pad_from_palm(
            rotated_image, rotated_palm_bbox)
        blob = cv.resize(crop, dsize=self.input_size,
                         interpolation=cv.INTER_AREA).astype(np.float32)
        blob = blob / 255.
        return (blob[np.newaxis, :, :, :], rotated_palm_bbox, angle,
                rotation_matrix, pad_bias)

    def infer(self, image, palm):
        """Returns (kp, conf): 21 (x, y) landmarks in image coords + overall
        confidence, or None if the crop no longer contains a hand."""
        (input_blob, rotated_palm_bbox, angle,
         rotation_matrix, pad_bias) = self._preprocess(image, palm)
        self.model.setInput(input_blob)
        output_blob = self.model.forward(
            self.model.getUnconnectedOutLayersNames())
        return self._postprocess(output_blob, rotated_palm_bbox, angle,
                                 rotation_matrix, pad_bias)

    def _postprocess(self, blob, rotated_palm_bbox, angle, rotation_matrix,
                     pad_bias):
        landmarks, conf = blob[0], blob[1]
        conf = float(conf[0][0])
        if conf < self.conf_threshold:
            return None

        landmarks = landmarks[0].reshape(-1, 3)  # (63,) -> (21, 3)
        # crop coords -> rotated-frame coords
        wh_rotated_palm_bbox = rotated_palm_bbox[1] - rotated_palm_bbox[0]
        scale_factor = wh_rotated_palm_bbox / self.input_size
        landmarks = ((landmarks[:, :2] - self.input_size / 2)
                     * max(scale_factor))
        coords_rotation_matrix = cv.getRotationMatrix2D((0, 0), angle, 1.0)
        rotated_landmarks = np.dot(landmarks, coords_rotation_matrix[:, :2])
        # undo the rotation to get original-frame coords
        rotation_component = np.array([
            [rotation_matrix[0][0], rotation_matrix[1][0]],
            [rotation_matrix[0][1], rotation_matrix[1][1]]])
        translation_component = np.array([
            rotation_matrix[0][2], rotation_matrix[1][2]])
        inverted_translation = np.array([
            -np.dot(rotation_component[0], translation_component),
            -np.dot(rotation_component[1], translation_component)])
        inverse_rotation_matrix = np.c_[rotation_component,
                                        inverted_translation]
        center = np.append(np.sum(rotated_palm_bbox, axis=0) / 2, 1)
        original_center = np.array([
            np.dot(center, inverse_rotation_matrix[0]),
            np.dot(center, inverse_rotation_matrix[1])])
        kp = rotated_landmarks + original_center + pad_bias
        return kp.astype(np.float32), conf


def palm_from_landmarks(kp):
    """Build a palm row for MPHandPose.infer() from the previous frame's 21
    landmarks, so tracking can continue without re-running palm detection
    (the same trick the MediaPipe pipeline uses)."""
    pts = kp[list(MPHandPose.PALM_LANDMARK_IDS)]
    bbox = np.r_[pts.min(axis=0), pts.max(axis=0)]
    return np.r_[bbox, pts.reshape(-1), 1.0].astype(np.float32)
