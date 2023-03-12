import torch
from mgds.DebugDataLoaderModules import *
from mgds.DiffusersDataLoaderModules import *
from mgds.GenericDataLoaderModules import *
from mgds.TrainDataSet import *
from mgds.TransformersDataLoaderModules import *
from diffusers import AutoencoderKL
from transformers import DPTForDepthEstimation, DPTImageProcessor, CLIPTokenizer

from trainer_util import *

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def create_dataset(
        model_variant: str, concepts: list[dict], cache_dir: str, batch_size: int, device: torch.device,
        vae: AutoencoderKL, tokenizer: CLIPTokenizer, image_depth_processor: DPTImageProcessor, depth_estimator: DPTForDepthEstimation
):
    input_modules = [
        CollectPaths(concept_in_name='concept', path_in_name='instance_data_dir', name_in_name='instance_prompt', path_out_name='image_path', concept_out_name='concept', extensions=['.png', '.jpg'], include_postfix=None, exclude_postfix=['-masklabel']),
        ModifyPath(in_name='image_path', out_name='mask_path', postfix='-masklabel', extension='.png'),
        ModifyPath(in_name='image_path', out_name='prompt_path', postfix='', extension='.txt'),
        LoadImage(path_in_name='image_path', image_out_name='image', range_min=-1.0, range_max=1.0),
        LoadImage(path_in_name='mask_path', image_out_name='mask', range_min=0, range_max=1, channels=1),
        GenerateDepth(path_in_name='image_path', image_out_name='depth', image_depth_processor=image_depth_processor, depth_estimator=depth_estimator) if model_variant == 'depth2img' else None,
        RandomMaskRotateCrop(mask_name='mask', additional_names=['image', 'depth'], min_size=512, min_padding_percent=10, max_padding_percent=30, max_rotate_angle=20) if model_variant == 'depth2img' else
        RandomMaskRotateCrop(mask_name='mask', additional_names=['image', ], min_size=512, min_padding_percent=10, max_padding_percent=30, max_rotate_angle=20),
        CalcAspect(image_in_name='image', resolution_out_name='original_resolution'),
        AspectBucketing(batch_size=batch_size, target_resolution=512, resolution_in_name='original_resolution', scale_resolution_out_name='scale_resolution', crop_resolution_out_name='crop_resolution'),
        ScaleCropImage(image_in_name='image', scale_resolution_in_name='scale_resolution', crop_resolution_in_name='crop_resolution', image_out_name='image'),
        ScaleCropImage(image_in_name='mask', scale_resolution_in_name='scale_resolution', crop_resolution_in_name='crop_resolution', image_out_name='mask'),
        ScaleCropImage(image_in_name='depth', scale_resolution_in_name='scale_resolution', crop_resolution_in_name='crop_resolution', image_out_name='depth') if model_variant == 'depth2img' else None,
        LoadText(path_in_name='prompt_path', text_out_name='prompt'),
        GenerateMaskedConditioningImage(image_in_name='image', mask_in_name='mask', image_out_name='conditioning_image'),
        # RandomFlip(names=['image', 'mask', 'depth', 'conditioning_image']),
        EncodeVAE(in_name='image', out_name='latent_image_distribution', vae=vae),
        Downscale(in_name='mask', out_name='latent_mask'),
        EncodeVAE(in_name='conditioning_image', out_name='latent_conditioning_image_distribution', vae=vae),
        Downscale(in_name='depth', out_name='latent_depth') if model_variant == 'depth2img' else None,
        Tokenize(in_name='prompt', out_name='tokens', tokenizer=tokenizer),
        DiskCache(cache_dir=cache_dir, split_names=['latent_image_distribution', 'latent_mask', 'latent_conditioning_image_distribution', 'latent_depth', 'tokens'], aggregate_names=['crop_resolution']) if model_variant == 'depth2img' else
        DiskCache(cache_dir=cache_dir, split_names=['latent_image_distribution', 'latent_mask', 'latent_conditioning_image_distribution', 'tokens'], aggregate_names=['crop_resolution']),
        SampleVAEDistribution(in_name='latent_image_distribution', out_name='latent_image', mode='mean'),
        SampleVAEDistribution(in_name='latent_conditioning_image_distribution', out_name='latent_conditioning_image', mode='mean'),
    ]

    debug_modules = [
        DecodeVAE(in_name='latent_image', out_name='decoded_image', vae=vae),
        DecodeVAE(in_name='latent_conditioning_image', out_name='decoded_conditioning_image', vae=vae),
        SaveImage(image_in_name='decoded_image', original_path_in_name='image_path', path='debug', in_range_min=-1, in_range_max=1),
        SaveImage(image_in_name='mask', original_path_in_name='image_path', path='debug', in_range_min=0, in_range_max=1),
        SaveImage(image_in_name='decoded_conditioning_image', original_path_in_name='image_path', path='debug', in_range_min=-1, in_range_max=1),
        # SaveImage(image_in_name='depth', original_path_in_name='image_path', path='debug', in_range_min=-1, in_range_max=1),
        # SaveImage(image_in_name='latent_mask', original_path_in_name='image_path', path='debug', in_range_min=0, in_range_max=1),
        # SaveImage(image_in_name='latent_depth', original_path_in_name='image_path', path='debug', in_range_min=-1, in_range_max=1),
    ]

    output_modules = [
        AspectBatchSorting(resolution_in_name='crop_resolution', names=['latent_image', 'latent_conditioning_image', 'latent_mask', 'latent_depth', 'tokens'], batch_size=batch_size) if model_variant == 'depth2img' else
        AspectBatchSorting(resolution_in_name='crop_resolution', names=['latent_image', 'latent_conditioning_image', 'latent_mask', 'tokens'], batch_size=batch_size),
    ]

    ds = TrainDataSet(
        torch.device(device),
        concepts,
        [
            input_modules,
            # debug_modules,
            output_modules
        ]
    )

    return ds
