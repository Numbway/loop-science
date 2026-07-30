FROM pytorch/pytorch:2.0.1-cuda11.7-cudnn8-runtime

RUN pip install --no-cache-dir tensorboard scikit-learn pandas matplotlib tqdm

WORKDIR /workspace
COPY runner.py /workspace/runner.py
