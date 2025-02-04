import os
import contextlib
import tarfile
import json
import numpy as np
import PIL
import torch
from common_utils import get_tmp_dir
import pickle
import random
from itertools import cycle
from torchvision.io.video import write_video
import unittest.mock
import hashlib
from distutils import dir_util
import re


def mock_class_attribute(stack, target, new):
    mock = unittest.mock.patch(target, new_callable=unittest.mock.PropertyMock, return_value=new)
    stack.enter_context(mock)
    return mock


def compute_md5(file):
    with open(file, "rb") as fh:
        return hashlib.md5(fh.read()).hexdigest()


def make_tar(root, name, *files, compression=None):
    ext = ".tar"
    mode = "w"
    if compression is not None:
        ext = f"{ext}.{compression}"
        mode = f"{mode}:{compression}"

    name = os.path.splitext(name)[0] + ext
    archive = os.path.join(root, name)

    with tarfile.open(archive, mode) as fh:
        for file in files:
            fh.add(os.path.join(root, file), arcname=file)

    return name, compute_md5(archive)


def clean_dir(root, *keep):
    pattern = re.compile(f"({f')|('.join(keep)})")
    for file_or_dir in os.listdir(root):
        if pattern.search(file_or_dir):
            continue

        file_or_dir = os.path.join(root, file_or_dir)
        if os.path.isfile(file_or_dir):
            os.remove(file_or_dir)
        else:
            dir_util.remove_tree(file_or_dir)


@contextlib.contextmanager
def mnist_root(num_images, cls_name):
    def _encode(v):
        return torch.tensor(v, dtype=torch.int32).numpy().tobytes()[::-1]

    def _make_image_file(filename, num_images):
        img = torch.randint(0, 256, size=(28 * 28 * num_images,), dtype=torch.uint8)
        with open(filename, "wb") as f:
            f.write(_encode(2051))  # magic header
            f.write(_encode(num_images))
            f.write(_encode(28))
            f.write(_encode(28))
            f.write(img.numpy().tobytes())

    def _make_label_file(filename, num_images):
        labels = torch.zeros((num_images,), dtype=torch.uint8)
        with open(filename, "wb") as f:
            f.write(_encode(2049))  # magic header
            f.write(_encode(num_images))
            f.write(labels.numpy().tobytes())

    with get_tmp_dir() as tmp_dir:
        raw_dir = os.path.join(tmp_dir, cls_name, "raw")
        os.makedirs(raw_dir)
        _make_image_file(os.path.join(raw_dir, "train-images-idx3-ubyte"), num_images)
        _make_label_file(os.path.join(raw_dir, "train-labels-idx1-ubyte"), num_images)
        _make_image_file(os.path.join(raw_dir, "t10k-images-idx3-ubyte"), num_images)
        _make_label_file(os.path.join(raw_dir, "t10k-labels-idx1-ubyte"), num_images)
        yield tmp_dir


@contextlib.contextmanager
def cifar_root(version):
    def _get_version_params(version):
        if version == 'CIFAR10':
            return {
                'base_folder': 'cifar-10-batches-py',
                'train_files': ['data_batch_{}'.format(batch) for batch in range(1, 6)],
                'test_file': 'test_batch',
                'target_key': 'labels',
                'meta_file': 'batches.meta',
                'classes_key': 'label_names',
            }
        elif version == 'CIFAR100':
            return {
                'base_folder': 'cifar-100-python',
                'train_files': ['train'],
                'test_file': 'test',
                'target_key': 'fine_labels',
                'meta_file': 'meta',
                'classes_key': 'fine_label_names',
            }
        else:
            raise ValueError

    def _make_pickled_file(obj, file):
        with open(file, 'wb') as fh:
            pickle.dump(obj, fh, 2)

    def _make_data_file(file, target_key):
        obj = {
            'data': np.zeros((1, 32 * 32 * 3), dtype=np.uint8),
            target_key: [0]
        }
        _make_pickled_file(obj, file)

    def _make_meta_file(file, classes_key):
        obj = {
            classes_key: ['fakedata'],
        }
        _make_pickled_file(obj, file)

    params = _get_version_params(version)
    with get_tmp_dir() as root:
        base_folder = os.path.join(root, params['base_folder'])
        os.mkdir(base_folder)

        for file in list(params['train_files']) + [params['test_file']]:
            _make_data_file(os.path.join(base_folder, file), params['target_key'])

        _make_meta_file(os.path.join(base_folder, params['meta_file']),
                        params['classes_key'])

        yield root


@contextlib.contextmanager
def widerface_root():
    """
    Generates a dataset with the following folder structure and returns the path root:
    <root>
        └── widerface
            ├── wider_face_split
            ├── WIDER_train
            ├── WIDER_val
            └── WIDER_test

    The dataset consist of
      1 image for each dataset split (train, val, test) and annotation files
      for each split
    """

    def _make_image(file):
        PIL.Image.fromarray(np.zeros((32, 32, 3), dtype=np.uint8)).save(file)

    def _make_train_archive(root):
        extracted_dir = os.path.join(root, 'WIDER_train', 'images', '0--Parade')
        os.makedirs(extracted_dir)
        _make_image(os.path.join(extracted_dir, '0_Parade_marchingband_1_1.jpg'))

    def _make_val_archive(root):
        extracted_dir = os.path.join(root, 'WIDER_val', 'images', '0--Parade')
        os.makedirs(extracted_dir)
        _make_image(os.path.join(extracted_dir, '0_Parade_marchingband_1_2.jpg'))

    def _make_test_archive(root):
        extracted_dir = os.path.join(root, 'WIDER_test', 'images', '0--Parade')
        os.makedirs(extracted_dir)
        _make_image(os.path.join(extracted_dir, '0_Parade_marchingband_1_3.jpg'))

    def _make_annotations_archive(root):
        train_bbox_contents = '0--Parade/0_Parade_marchingband_1_1.jpg\n1\n449 330 122 149 0 0 0 0 0 0\n'
        val_bbox_contents = '0--Parade/0_Parade_marchingband_1_2.jpg\n1\n501 160 285 443 0 0 0 0 0 0\n'
        test_filelist_contents = '0--Parade/0_Parade_marchingband_1_3.jpg\n'
        extracted_dir = os.path.join(root, 'wider_face_split')
        os.mkdir(extracted_dir)

        # bbox training file
        bbox_file = os.path.join(extracted_dir, "wider_face_train_bbx_gt.txt")
        with open(bbox_file, "w") as txt_file:
            txt_file.write(train_bbox_contents)

        # bbox validation file
        bbox_file = os.path.join(extracted_dir, "wider_face_val_bbx_gt.txt")
        with open(bbox_file, "w") as txt_file:
            txt_file.write(val_bbox_contents)

        # test filelist file
        filelist_file = os.path.join(extracted_dir, "wider_face_test_filelist.txt")
        with open(filelist_file, "w") as txt_file:
            txt_file.write(test_filelist_contents)

    with get_tmp_dir() as root:
        root_base = os.path.join(root, "widerface")
        os.mkdir(root_base)
        _make_train_archive(root_base)
        _make_val_archive(root_base)
        _make_test_archive(root_base)
        _make_annotations_archive(root_base)

        yield root


@contextlib.contextmanager
def places365_root(split="train-standard", small=False):
    VARIANTS = {
        "train-standard": "standard",
        "train-challenge": "challenge",
        "val": "standard",
    }
    # {split: file}
    DEVKITS = {
        "train-standard": "filelist_places365-standard.tar",
        "train-challenge": "filelist_places365-challenge.tar",
        "val": "filelist_places365-standard.tar",
    }
    CATEGORIES = "categories_places365.txt"
    # {split: file}
    FILE_LISTS = {
        "train-standard": "places365_train_standard.txt",
        "train-challenge": "places365_train_challenge.txt",
        "val": "places365_train_standard.txt",
    }
    # {(split, small): (archive, folder_default, folder_renamed)}
    IMAGES = {
        ("train-standard", False): ("train_large_places365standard.tar", "data_large", "data_large_standard"),
        ("train-challenge", False): ("train_large_places365challenge.tar", "data_large", "data_large_challenge"),
        ("val", False): ("val_large.tar", "val_large", "val_large"),
        ("train-standard", True): ("train_256_places365standard.tar", "data_256", "data_256_standard"),
        ("train-challenge", True): ("train_256_places365challenge.tar", "data_256", "data_256_challenge"),
        ("val", True): ("val_256.tar", "val_256", "val_256"),
    }

    # (class, idx)
    CATEGORIES_CONTENT = (("/a/airfield", 0), ("/a/apartment_building/outdoor", 8), ("/b/badlands", 30))
    # (file, idx)
    FILE_LIST_CONTENT = (
        ("Places365_val_00000001.png", 0),
        *((f"{category}/Places365_train_00000001.png", idx) for category, idx in CATEGORIES_CONTENT),
    )

    def mock_target(attr, partial="torchvision.datasets.places365.Places365"):
        return f"{partial}.{attr}"

    def make_txt(root, name, seq):
        file = os.path.join(root, name)
        with open(file, "w") as fh:
            for string, idx in seq:
                fh.write(f"{string} {idx}\n")
        return name, compute_md5(file)

    def make_categories_txt(root, name):
        return make_txt(root, name, CATEGORIES_CONTENT)

    def make_file_list_txt(root, name):
        return make_txt(root, name, FILE_LIST_CONTENT)

    def make_image(file, size):
        os.makedirs(os.path.dirname(file), exist_ok=True)
        PIL.Image.fromarray(np.zeros((*size, 3), dtype=np.uint8)).save(file)

    def make_devkit_archive(stack, root, split):
        archive = DEVKITS[split]
        files = []

        meta = make_categories_txt(root, CATEGORIES)
        mock_class_attribute(stack, mock_target("_CATEGORIES_META"), meta)
        files.append(meta[0])

        meta = {split: make_file_list_txt(root, FILE_LISTS[split])}
        mock_class_attribute(stack, mock_target("_FILE_LIST_META"), meta)
        files.extend([item[0] for item in meta.values()])

        meta = {VARIANTS[split]: make_tar(root, archive, *files)}
        mock_class_attribute(stack, mock_target("_DEVKIT_META"), meta)

    def make_images_archive(stack, root, split, small):
        archive, folder_default, folder_renamed = IMAGES[(split, small)]

        image_size = (256, 256) if small else (512, random.randint(512, 1024))
        files, idcs = zip(*FILE_LIST_CONTENT)
        images = [file.lstrip("/").replace("/", os.sep) for file in files]
        for image in images:
            make_image(os.path.join(root, folder_default, image), image_size)

        meta = {(split, small): make_tar(root, archive, folder_default)}
        mock_class_attribute(stack, mock_target("_IMAGES_META"), meta)

        return [(os.path.join(root, folder_renamed, image), idx) for image, idx in zip(images, idcs)]

    with contextlib.ExitStack() as stack, get_tmp_dir() as root:
        make_devkit_archive(stack, root, split)
        class_to_idx = dict(CATEGORIES_CONTENT)
        classes = list(class_to_idx.keys())

        data = {"class_to_idx": class_to_idx, "classes": classes}
        data["imgs"] = make_images_archive(stack, root, split, small)

        clean_dir(root, ".tar$")

        yield root, data


@contextlib.contextmanager
def stl10_root(_extracted=False):
    CLASS_NAMES = ("airplane", "bird")
    ARCHIVE_NAME = "stl10_binary"
    NUM_FOLDS = 10

    def mock_target(attr, partial="torchvision.datasets.stl10.STL10"):
        return f"{partial}.{attr}"

    def make_binary_file(num_elements, root, name):
        file = os.path.join(root, name)
        np.zeros(num_elements, dtype=np.uint8).tofile(file)
        return name, compute_md5(file)

    def make_image_file(num_images, root, name, num_channels=3, height=96, width=96):
        return make_binary_file(num_images * num_channels * height * width, root, name)

    def make_label_file(num_images, root, name):
        return make_binary_file(num_images, root, name)

    def make_class_names_file(root, name="class_names.txt"):
        with open(os.path.join(root, name), "w") as fh:
            for name in CLASS_NAMES:
                fh.write(f"{name}\n")

    def make_fold_indices_file(root):
        offset = 0
        with open(os.path.join(root, "fold_indices.txt"), "w") as fh:
            for fold in range(NUM_FOLDS):
                line = " ".join([str(idx) for idx in range(offset, offset + fold + 1)])
                fh.write(f"{line}\n")
                offset += fold + 1

        return tuple(range(1, NUM_FOLDS + 1))

    def make_train_files(stack, root, num_unlabeled_images=1):
        num_images_in_fold = make_fold_indices_file(root)
        num_train_images = sum(num_images_in_fold)

        train_list = [
            list(make_image_file(num_train_images, root, "train_X.bin")),
            list(make_label_file(num_train_images, root, "train_y.bin")),
            list(make_image_file(1, root, "unlabeled_X.bin"))
        ]
        mock_class_attribute(stack, target=mock_target("train_list"), new=train_list)

        return num_images_in_fold, dict(train=num_train_images, unlabeled=num_unlabeled_images)

    def make_test_files(stack, root, num_images=2):
        test_list = [
            list(make_image_file(num_images, root, "test_X.bin")),
            list(make_label_file(num_images, root, "test_y.bin")),
        ]
        mock_class_attribute(stack, target=mock_target("test_list"), new=test_list)

        return dict(test=num_images)

    def make_archive(stack, root, name):
        archive, md5 = make_tar(root, name, name, compression="gz")
        mock_class_attribute(stack, target=mock_target("tgz_md5"), new=md5)
        return archive

    with contextlib.ExitStack() as stack, get_tmp_dir() as root:
        archive_folder = os.path.join(root, ARCHIVE_NAME)
        os.mkdir(archive_folder)

        num_images_in_folds, num_images_in_split = make_train_files(stack, archive_folder)
        num_images_in_split.update(make_test_files(stack, archive_folder))

        make_class_names_file(archive_folder)

        archive = make_archive(stack, root, ARCHIVE_NAME)

        dir_util.remove_tree(archive_folder)
        data = dict(num_images_in_folds=num_images_in_folds, num_images_in_split=num_images_in_split, archive=archive)

        yield root, data
