# Firebase 配置说明

## 🔥 如何配置Firebase

### 第一步：创建Firebase项目

1. 访问 [Firebase Console](https://console.firebase.google.com/)
2. 点击 **"添加项目"**
3. 输入项目名称：`TouringBank`
4. 点击 **"创建项目"**

### 第二步：注册Web应用

1. 在项目概览页面，点击 **Web图标** (`</>`)
2. 输入应用昵称：`TouringBank Web`
3. 点击 **"注册应用"**
4. **复制配置代码**

### 第三步：启用Authentication

1. 在左侧菜单选择 **"Authentication"**
2. 点击 **"开始使用"**
3. 选择 **"Sign-in method"** 标签
4. 启用以下登录方式：
   - ✅ **电子邮件/密码** (Email/Password)
   - ✅ **Google** (可选)
   - ✅ **GitHub** (可选)

### 第四步：配置您的项目

打开文件：`js/firebase-config.js`

将以下配置替换为您从Firebase Console获取的实际配置：

```javascript
const firebaseConfig = {
  apiKey: "YOUR_API_KEY_HERE",
  authDomain: "YOUR_PROJECT_ID.firebaseapp.com",
  projectId: "YOUR_PROJECT_ID",
  storageBucket: "YOUR_PROJECT_ID.appspot.com",
  messagingSenderId: "YOUR_MESSAGING_SENDER_ID",
  appId: "YOUR_APP_ID"
};
```

## ✅ 测试登录功能

### 方法1：创建测试账户

1. 在Firebase Console的Authentication页面
2. 点击 **"Users"** 标签
3. 点击 **"Add user"**
4. 输入邮箱和密码
5. 使用该账户在Login.html页面登录

### 方法2：直接注册

1. 访问 `Register.html` 页面
2. 填写邮箱和密码
3. 点击注册
4. 使用注册的账户登录

## 📚 已实现的功能

- ✅ 邮箱密码登录
- ✅ Google第三方登录
- ✅ GitHub第三方登录
- ✅ 密码重置（忘记密码）
- ✅ 记住我功能
- ✅ 用户注册
- ✅ 登录状态管理

## 🔧 故障排除

### 问题：点击登录没有反应

**解决方案：**
1. 打开浏览器控制台（F12）
2. 查看是否有错误信息
3. 确认已正确配置 `firebase-config.js`
4. 确认Firebase项目已启用Authentication

### 问题：显示"auth/configuration-not-found"

**解决方案：**
1. 检查 `firebase-config.js` 中的配置是否正确
2. 确认Firebase项目ID是否匹配

### 问题：Google登录失败

**解决方案：**
1. 在Firebase Console的Authentication > Sign-in method中启用Google登录
2. 确认授权域名已添加（localhost应该默认已添加）

## 📞 需要帮助？

如果遇到问题，请查看：
- [Firebase Authentication 文档](https://firebase.google.com/docs/auth)
- [Firebase Web SDK 参考](https://firebase.google.com/docs/reference/js)
