#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B站视频信息和字幕获取增强工具

添加了凭证支持以解决字幕获取问题
支持有凭证和无凭证两种模式
"""

import json
import random
import re
import time
import urllib.parse
from functools import reduce
from hashlib import md5
from http.cookies import SimpleCookie
from typing import Optional, Dict, List, Any

import httpx


# 现代化的请求头
HEADERS = {
    "authority": "api.bilibili.com",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "zh-CN,zh;q=0.9",
    "cache-control": "no-cache",
    "dnt": "1",
    "pragma": "no-cache",
    "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}

# WBI签名相关
mixinKeyEncTab = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]

def getMixinKey(orig: str):
    return reduce(lambda s, i: s + orig[i], mixinKeyEncTab, "")[:32]

def encWbi(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = getMixinKey(img_key + sub_key)
    curr_time = round(time.time())
    params["wts"] = curr_time
    params = dict(sorted(params.items()))
    params = {
        k: "".join(filter(lambda chr: chr not in "!'()*", str(v)))
        for k, v in params.items()
    }
    query = urllib.parse.urlencode(params)
    wbi_sign = md5((query + mixin_key).encode()).hexdigest()
    params["w_rid"] = wbi_sign
    return params

def getWbiKeys() -> tuple[str, str]:
    resp = httpx.get("https://api.bilibili.com/x/web-interface/nav", headers=HEADERS)
    resp.raise_for_status()
    json_content = resp.json()
    img_url: str = json_content["data"]["wbi_img"]["img_url"]
    sub_url: str = json_content["data"]["wbi_img"]["sub_url"]
    img_key = img_url.rsplit("/", 1)[1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
    return img_key, sub_key

def get_signed_params(params: dict) -> dict:
    img_key, sub_key = getWbiKeys()
    return encWbi(params, img_key, sub_key)

def parse_cookies(cookie_str):
    cookie = SimpleCookie()
    cookie.load(cookie_str)
    return {key: morsel.value for key, morsel in cookie.items()}

class BilibiliEnhancedTool:
    """B站视频信息和字幕获取增强工具
    
    此工具需要用户提供有效的B站登录凭证（SESSDATA、bili_jct、buvid3）才能使用。
    所有凭证参数都是必需的，缺少任何一个都会导致初始化失败。
    
    主要功能包括：
    - 获取视频基本信息
    - 获取视频分P信息
    - 获取视频字幕信息和内容
    - BV号和AV号相互转换
    """
    
    def __init__(self, sessdata, bili_jct, buvid3):
        """
        初始化工具
        
        Args:
            sessdata: 用户会话数据（必需）
            bili_jct: 用户验证令牌（必需）
            buvid3: 用户设备标识（必需）
        
        Raises:
            ValueError: 如果任何凭证参数为空或None
        """
        # 检查所有凭证是否都已提供
        if not sessdata or not bili_jct or not buvid3:
            missing_credentials = []
            if not sessdata:
                missing_credentials.append('sessdata')
            if not bili_jct:
                missing_credentials.append('bili_jct')
            if not buvid3:
                missing_credentials.append('buvid3')
            raise ValueError(f"所有凭证参数都是必需的。缺少: {', '.join(missing_credentials)}")
        
        # 设置用户凭证
        self.cookies = {
            'SESSDATA': sessdata,
            'bili_jct': bili_jct,
            'buvid3': buvid3
        }
        self.has_credentials = True
    

    
    def _make_request(self, url: str, params: dict = None, use_wbi: bool = True) -> dict:
        """发起HTTP请求的辅助方法"""
        try:
            # 如果需要WBI签名，对参数进行签名
            if use_wbi and params:
                params = get_signed_params(params)
            
            with httpx.Client() as client:
                response = client.get(
                    url=url,
                    params=params,
                    headers=HEADERS,
                    cookies=self.cookies,
                    timeout=10
                )
                response.raise_for_status()
                return response.json()
            
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP错误 {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"请求错误: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"JSON解析错误: {e}")
        except Exception as e:
            raise Exception(f"请求失败: {e}")
    
    def bvid2aid(self, bvid: str) -> int:
        """BV号转AV号"""
        # 基于bilibili_api项目的转换算法
        XOR_CODE = 23442827791579
        MASK_CODE = 2251799813685247
        BASE = 58
        
        data = [
            b"F", b"c", b"w", b"A", b"P", b"N", b"K", b"T", b"M", b"u", b"g", b"3", b"G", b"V", b"5", b"L",
            b"j", b"7", b"E", b"J", b"n", b"H", b"p", b"W", b"s", b"x", b"4", b"t", b"b", b"8", b"h", b"a",
            b"Y", b"e", b"v", b"i", b"q", b"B", b"z", b"6", b"r", b"k", b"C", b"y", b"1", b"2", b"m", b"U",
            b"S", b"D", b"Q", b"X", b"9", b"R", b"d", b"o", b"Z", b"f"
        ]
        
        bvid = list(bvid)
        bvid[3], bvid[9] = bvid[9], bvid[3]
        bvid[4], bvid[7] = bvid[7], bvid[4]
        bvid = bvid[3:]
        tmp = 0
        for i in bvid:
            idx = data.index(i.encode())
            tmp = tmp * BASE + idx
        return (tmp & MASK_CODE) ^ XOR_CODE
    
    def aid2bvid(self, aid: int) -> str:
        """AV号转BV号"""
        XOR_CODE = 23442827791579
        MAX_AID = 1 << 51
        BASE = 58
        BV_LEN = 12
        
        data = [
            b"F", b"c", b"w", b"A", b"P", b"N", b"K", b"T", b"M", b"u", b"g", b"3", b"G", b"V", b"5", b"L",
            b"j", b"7", b"E", b"J", b"n", b"H", b"p", b"W", b"s", b"x", b"4", b"t", b"b", b"8", b"h", b"a",
            b"Y", b"e", b"v", b"i", b"q", b"B", b"z", b"6", b"r", b"k", b"C", b"y", b"1", b"2", b"m", b"U",
            b"S", b"D", b"Q", b"X", b"9", b"R", b"d", b"o", b"Z", b"f"
        ]
        
        bytes_list = [b"B", b"V", b"1", b"0", b"0", b"0", b"0", b"0", b"0", b"0", b"0", b"0"]
        bv_idx = BV_LEN - 1
        tmp = (MAX_AID | aid) ^ XOR_CODE
        while int(tmp) != 0:
            bytes_list[bv_idx] = data[int(tmp % BASE)]
            tmp //= BASE
            bv_idx -= 1
        bytes_list[3], bytes_list[9] = bytes_list[9], bytes_list[3]
        bytes_list[4], bytes_list[7] = bytes_list[7], bytes_list[4]
        return "".join([i.decode() for i in bytes_list])
    
    def get_video_info(self, video_id: str) -> Optional[Dict[str, Any]]:
        """获取视频基本信息
        
        Args:
            video_id: 视频ID，支持BV号或AV号
            
        Returns:
            Dict: 视频信息字典，失败返回None
        """
        try:
            # 判断是BV号还是AV号
            if video_id.startswith('BV'):
                bvid = video_id
                aid = self.bvid2aid(bvid)
            elif video_id.startswith('av') or video_id.isdigit():
                aid = int(video_id.replace('av', ''))
                bvid = self.aid2bvid(aid)
            else:
                print(f"无效的视频ID格式: {video_id}")
                return None
            
            # 调用B站API获取视频信息
            url = "https://api.bilibili.com/x/web-interface/view"
            params = {
                'bvid': bvid
            }
            
            data = self._make_request(url, params)
            if data.get('code') != 0:
                print(f"API返回错误: {data.get('message', '未知错误')}")
                return None
            
            video_data = data.get('data', {})
            
            # 提取关键信息
            info = {
                'aid': video_data.get('aid'),
                'bvid': video_data.get('bvid'),
                'title': video_data.get('title'),
                'desc': video_data.get('desc'),
                'duration': video_data.get('duration'),
                'pubdate': video_data.get('pubdate'),
                'owner': video_data.get('owner', {}),
                'stat': video_data.get('stat', {}),
                'pages': video_data.get('pages', [])
            }
            
            return info
            
        except Exception as e:
            print(f"获取视频信息失败: {e}")
            return None
    
    def get_video_pages(self, video_id: str) -> Optional[List[Dict[str, Any]]]:
        """获取视频分P信息
        
        Args:
            video_id: 视频ID，支持BV号或AV号
            
        Returns:
            List: 分P信息列表，失败返回None
        """
        try:
            # 判断是BV号还是AV号
            if video_id.startswith('BV'):
                bvid = video_id
                aid = self.bvid2aid(bvid)
            elif video_id.startswith('av') or video_id.isdigit():
                aid = int(video_id.replace('av', ''))
                bvid = self.aid2bvid(aid)
            else:
                print(f"无效的视频ID格式: {video_id}")
                return None
            
            # 调用B站API获取分P信息
            url = "https://api.bilibili.com/x/player/pagelist"
            params = {
                'bvid': bvid
            }
            
            data = self._make_request(url, params, use_wbi=False)
            if data.get('code') != 0:
                print(f"API返回错误: {data.get('message', '未知错误')}")
                return None
            
            return data.get('data', [])
            
        except Exception as e:
            print(f"获取分P信息失败: {e}")
            return None
    
    def get_player_info(self, video_id: str, cid: int) -> Optional[Dict[str, Any]]:
        """获取播放器信息（包含字幕链接）
        
        Args:
            video_id: 视频ID（BV号或AV号）
            cid: 分P的cid
            
        Returns:
            Dict: 播放器信息，包含字幕链接等
        """
        try:
            # 确保使用BV号
            if video_id.startswith('av') or video_id.isdigit():
                aid = int(video_id.replace('av', ''))
                bvid = self.aid2bvid(aid)
            else:
                bvid = video_id
                aid = self.bvid2aid(video_id)
            
            # 使用播放器接口 - 使用wbi接口获取完整字幕信息
            url = "https://api.bilibili.com/x/player/wbi/v2"
            params = {
                'bvid': bvid,
                'cid': cid
            }
            
            data = self._make_request(url, params)
            if data.get('code') != 0:
                print(f"WBI API返回错误: {data.get('message', '未知错误')}")
                # 如果wbi接口失败，尝试普通接口
                return self._get_player_info_fallback(aid, cid)
            
            return data.get('data', {})
            
        except Exception as e:
            print(f"获取播放器信息失败: {e}")
            # 尝试备用方法
            return self._get_player_info_fallback(aid if 'aid' in locals() else self.bvid2aid(video_id), cid)
    
    def _get_player_info_fallback(self, aid: int, cid: int) -> Optional[Dict[str, Any]]:
        """备用的播放器信息获取方法"""
        try:
            url = "https://api.bilibili.com/x/player/v2"
            params = {
                'aid': aid,
                'cid': cid
            }
            
            data = self._make_request(url, params, use_wbi=False)
            if data.get('code') != 0:
                print(f"备用API返回错误: {data.get('message', '未知错误')}")
                return None
            
            return data.get('data', {})
            
        except Exception as e:
            print(f"备用方法获取播放器信息失败: {e}")
            return None
    
    def get_subtitle_info(self, video_id: str, cid: int) -> Optional[List[Dict[str, Any]]]:
        """获取视频字幕信息
        
        Args:
            video_id: 视频ID，支持BV号或AV号
            cid: 分P的cid
            
        Returns:
            List: 字幕信息列表，失败返回None
        """
        try:
            # 获取播放器信息
            player_info = self.get_player_info(video_id, cid)
            if not player_info:
                return None
            
            # 提取字幕信息
            subtitle_info = player_info.get('subtitle', {})
            subtitles = subtitle_info.get('subtitles', [])
            
            return subtitles
            
        except Exception as e:
            print(f"获取字幕信息失败: {e}")
            return None
    
    def download_subtitle(self, subtitle_url: str) -> Optional[List[Dict[str, Any]]]:
        """下载字幕内容
        
        Args:
            subtitle_url: 字幕文件URL
            
        Returns:
            List: 字幕内容列表，失败返回None
        """
        try:
            # 确保URL是完整的
            if subtitle_url.startswith('//'):
                subtitle_url = 'https:' + subtitle_url
            
            data = self._make_request(subtitle_url)
            return data.get('body', [])
            
        except Exception as e:
            print(f"下载字幕失败: {e}")
            return None
    
    def get_subtitle_content(self, subtitle_url: str) -> Optional[str]:
        """获取字幕内容
        
        Args:
            subtitle_url: 字幕文件URL
            
        Returns:
            str: 字幕内容，失败返回None
        """
        try:
            # 确保URL是完整的
            if subtitle_url.startswith('//'):
                subtitle_url = 'https:' + subtitle_url
            elif subtitle_url.startswith('/'):
                subtitle_url = 'https://api.bilibili.com' + subtitle_url
            
            # 使用httpx直接请求字幕文件
            with httpx.Client(headers=HEADERS, cookies=self.cookies, timeout=10) as client:
                response = client.get(subtitle_url)
                response.raise_for_status()
                content = response.text
            
            # 解析JSON格式的字幕
            subtitle_data = json.loads(content)
            
            # 提取字幕文本
            subtitle_text = ""
            if 'body' in subtitle_data:
                for item in subtitle_data['body']:
                    if 'content' in item:
                        subtitle_text += item['content'] + "\n"
            
            return subtitle_text.strip()
            
        except Exception as e:
            print(f"获取字幕内容失败: {e}")
            return None
    
    def get_video_subtitle(self, video_id: str, page: int = 1, lang: str = 'zh') -> Optional[str]:
        """获取视频字幕文本
        
        Args:
            video_id: 视频ID，支持BV号或AV号
            page: 分P页码，从1开始
            lang: 字幕语言，默认中文
            
        Returns:
            str: 字幕文本，失败返回None
        """
        try:
            # 获取分P信息
            pages = self.get_video_pages(video_id)
            if not pages or page > len(pages):
                print(f"无效的分P页码: {page}")
                return None
            
            cid = pages[page - 1].get('cid')
            
            # 获取字幕信息
            subtitle_info = self.get_subtitle_info(video_id, cid)
            if not subtitle_info:
                return None
            
            # 查找指定语言的字幕
            target_subtitle = None
            for subtitle in subtitle_info:
                if lang in subtitle.get('lan', ''):
                    target_subtitle = subtitle
                    break
            
            #print(f"所有可用字幕: {[(s.get('lan'), s.get('lan_doc')) for s in subtitle_info]}")

            # 如果没找到指定语言，使用第一个可用的字幕
            if not target_subtitle and subtitle_info:
                target_subtitle = subtitle_info[0]
                print(f"未找到{lang}字幕，使用{target_subtitle.get('lan_doc', '未知语言')}字幕")
            
            if not target_subtitle:
                print("没有可用的字幕")
                return None
            
            # 下载字幕内容
            subtitle_url = target_subtitle.get('subtitle_url')
            if not subtitle_url:
                print("字幕URL为空")
                return None
            
            subtitle_content = self.download_subtitle(subtitle_url)
            if not subtitle_content:
                return None
            
            # 拼接字幕文本
            subtitle_text = ''
            for item in subtitle_content:
                content = item.get('content', '').strip()
                if content:
                    subtitle_text += content + '\n'
            
            return subtitle_text.strip()
            
        except Exception as e:
            print(f"获取字幕文本失败: {e}")
            return None    
    def get_credentials_status(self) -> Dict[str, Any]:
        """获取凭证状态信息"""
        return {
            'has_credentials': self.has_credentials,
            'cookies': self.cookies,
            'can_access_subtitles': self.has_credentials
        }


def main():
    """主函数，演示工具使用"""
    print("=== B站视频信息和字幕获取增强工具演示 ===")
    
    # 测试视频ID
    test_video_id = "BV1GJ411x7h7"
    
    print(f"\n测试视频: {test_video_id}")
    print("注意：此工具需要提供有效的B站登录凭证才能使用")
    
    # 示例凭证（需要替换为真实值）
    SESSDATA = "your_sessdata_here"
    BILI_JCT = "your_bili_jct_here"
    BUVID3 = "your_buvid3_here"
    
    if SESSDATA != "your_sessdata_here":
        print("\n=== 使用真实凭证测试 ===")
        try:
            tool = BilibiliEnhancedTool(SESSDATA, BILI_JCT, BUVID3)
            print(f"凭证状态: {tool.get_credentials_status()}")
            
            # 获取视频信息
            video_info = tool.get_video_info(test_video_id)
            if video_info:
                print(f"✓ 视频标题: {video_info['title']}")
                print(f"✓ 视频作者: {video_info['owner']['name']}")
                print(f"✓ 视频时长: {video_info['duration']}秒")
            
            # 尝试获取字幕
            subtitle_text = tool.get_video_subtitle(test_video_id)
            if subtitle_text:
                print(f"✓ 字幕获取成功，长度: {len(subtitle_text)}字符")
                lines = subtitle_text.split('\n')[:5]
                print("字幕预览:")
                for i, line in enumerate(lines, 1):
                    if line.strip():
                        print(f"  {i}. {line}")
            else:
                print("✗ 字幕获取失败")
                
        except ValueError as e:
            print(f"✗ 凭证验证失败: {e}")
        except Exception as e:
            print(f"✗ 工具初始化失败: {e}")
    else:
        print("\n=== 演示凭证验证 ===")
        print("尝试使用空凭证初始化工具...")
        try:
            tool = BilibiliEnhancedTool("", "", "")
        except ValueError as e:
            print(f"✓ 凭证验证正常工作: {e}")
        
        print("\n请在代码中填入真实的用户凭证进行完整测试:")  
        print("1. 打开浏览器，登录bilibili.com")
        print("2. 按F12打开开发者工具")
        print("3. 在Application/Storage -> Cookies中找到:")
        print("   - SESSDATA")
        print("   - bili_jct")
        print("   - buvid3")
        print("4. 将这些值填入代码中的对应变量")


if __name__ == "__main__":
    main()
