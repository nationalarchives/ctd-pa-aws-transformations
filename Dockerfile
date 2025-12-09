# Use AWS Lambda Python 3.11 base image
FROM public.ecr.aws/lambda/python:3.12

# Install system dependencies (if any)
RUN yum install -y gcc python3-devel && yum clean all

# Copy and install Python dependencies
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r requirements.txt --target ${LAMBDA_TASK_ROOT}

# Copy source code (transformers and utilities)
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Copy Lambda handler
COPY lambda_handler.py ${LAMBDA_TASK_ROOT}/

# Verify structure (optional, for debugging during build)
RUN ls -la ${LAMBDA_TASK_ROOT} && ls -la ${LAMBDA_TASK_ROOT}/src/

# Set the Lambda handler
CMD [ "lambda_handler.lambda_handler" ]
