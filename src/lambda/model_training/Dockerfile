FROM public.ecr.aws/lambda/python:3.12

COPY src/lambda/model_training/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY src/lambda/model_training/handler.py ${LAMBDA_TASK_ROOT}/handler.py
COPY ml/train_baseline.py ${LAMBDA_TASK_ROOT}/train_baseline.py

CMD ["handler.handler"]
