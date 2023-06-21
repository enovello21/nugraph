#!/usr/bin/env python
#SBATCH -J exatrkx_train
#SBATCH -t 1440
#SBATCH -p gpu_gce
#SBATCH -x wcgwn[003-008]
#SBATCH --gres=gpu:1
#SBATCH -A fwk
#SBATCH -q regular
#SBATCH --cpus-per-task=12

import sys
import os
import argparse
import torch
import pytorch_lightning as pl
from pytorch_lightning.plugins.environments import SLURMEnvironment
from pytorch_lightning.callbacks import LearningRateMonitor
import nugraph as ng
import signal

import warnings
warnings.filterwarnings('ignore', '.*TypedStorage is deprecated.*')

Data = ng.data.H5DataModule
Model = ng.models.NuGraph2

def configure():
    parser = argparse.ArgumentParser(sys.argv[0])
    parser.add_argument('--name', type=str, default=None,
                        help='Training instance name, for logging purposes')
    parser.add_argument('--logdir', type=str, default=None,
                        help='Output directory to write logs to')
    parser.add_argument('--resume', type=str, default=None,
                        help='Checkpoint file to resume training from')
    parser.add_argument('--profiler', type=str, default=None,
                        help='Enable requested profiler')
    parser = Data.add_data_args(parser)
    parser = Model.add_model_args(parser)
    parser = Model.add_train_args(parser)
    return parser.parse_args()

def train(args):

    torch.manual_seed(1)

    # Load dataset
    nudata = Data(args.data_path, batch_size=args.batch_size)

    if args.name is not None and args.logdir is not None and args.resume is None:
        model = Model(in_features=4,
                      node_features=args.node_feats,
                      edge_features=args.edge_feats,
                      sp_features=args.sp_feats,
                      planes=nudata.planes,
                      classes=nudata.classes,
                      num_iters=5,
                      event_head=args.event,
                      semantic_head=args.semantic,
                      filter_head=args.filter,
                      checkpoint=not args.no_checkpointing,
                      lr=args.learning_rate)
        name = args.name
        logdir = args.logdir
        version = None
        os.makedirs(os.path.join(logdir, args.name), exist_ok=True)
    elif args.resume is not None and args.name is None and args.logdir is None:
        model = Model.load_from_checkpoint(args.resume)
        stub = os.path.dirname(os.path.dirname(args.resume))
        stub, version = os.path.split(stub)
        logdir, name = os.path.split(stub)
    else:
        raise Exception('You must pass either the --name and --logdir arguments to start an existing training, or the --resume argument to resume an existing one.')

    logger = pl.loggers.TensorBoardLogger(save_dir=logdir,
                                          name=name, version=version,
                                          default_hp_metric=False)

    callbacks = [
        LearningRateMonitor(logging_interval='step')
    ]

    devices = 'auto'
    device_count = torch.cuda.device_count()
    if device_count > 1:
        devices = { i: torch.cuda.mem_get_info(i)[0] for i in range(device_count) }
        devices = [ max(devices, key=devices.get) ]
        print('Multiple GPUs detected, selected device', *devices)

    trainer = pl.Trainer(devices=devices,
                         max_epochs=args.epochs,
                         limit_train_batches=args.limit_train_batches,
                         limit_val_batches=args.limit_val_batches,
                         logger=logger,
                         profiler=args.profiler,
                         callbacks=callbacks)

    trainer.fit(model, datamodule=nudata, ckpt_path=args.resume)

if __name__ == '__main__':
    args = configure()
    train(args)
