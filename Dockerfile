# 卤味小店 · 网页 + 微信支付服务器
# 零依赖：不需要 npm install
#
# 构建（在 luhuo/ 目录下）：
#   docker build -t luhuo-pay .
# 运行：
#   docker run -d --name luhuo-pay -p 8787:8787 \
#     -e MOCK=1 \
#     -v $(pwd)/server/data:/app/server/data \
#     luhuo-pay

FROM node:20-alpine

# 时区（订单时间显示用）
RUN apk add --no-cache tzdata && \
    cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone

WORKDIR /app

# 整个卤味项目（网页 + server）一起进去
COPY . /app

# 跟着平台给什么端口就用什么端口
ENV PORT=8787
ENV NODE_ENV=production
EXPOSE 8787

# 健康检查：容器挂了自动重启
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||8787)+'/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

WORKDIR /app/server
CMD ["node", "index.js"]
