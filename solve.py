def top_k_frequent(nums, k):
    if not nums or k <= 0:
        return []
    freq = {}
    for num in nums:
        freq[num] = freq.get(num, 0) + 1
        
        sorted_items = sorted(freq.items(),
                              key=lambda item: (-item[1], item[0]))
        return [num for num, count in 
                sorted_items[:k]]
        
        #Example usage:
        print(top_k_frequent([4,1,4,2,1,4,3,2], 2)) #[4, 1]
        print(top_k_frequent([5, 2, 5, 2,3], 3))
        #[2, 5, 3]
        print(top_k_frequent([], 2))
        #[]